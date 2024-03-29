# -*- coding: utf-8 -*-
"""
RT Sql Layer
Copyright 2010 Giuseppe Sucameli

based on PostGIS Manager
Copyright 2008 Martin Dobias

Licensed under the terms of GNU GPL v2 (or any later)
http://www.gnu.org/copyleft/gpl.html


Good resource for metadata extraction:
http://www.alberton.info/postgresql_meta_info.html
System information functions:
http://www.postgresql.org/docs/8.0/static/functions-info.html
"""

from PyQt4.QtCore import *
from PyQt4.QtGui import *

import qgis.core

import psycopg2
import psycopg2.extensions # for isolation levels

from .. import dbConnection as DbConn
from .. import orientationMapsCreator_utils as Utils

import re

# use unicode!
psycopg2.extensions.register_type(psycopg2.extensions.UNICODE)


class TableAttribute(DbConn.TableAttribute):
	def __init__(self, row):
		self.num, self.name, self.data_type, self.char_max_len, self.modifier, self.notnull, self.hasdefault, self.default = row


class TableConstraint(DbConn.TableConstraint):
	""" class that represents a constraint of a table (relation) """

	def __init__(self, row):
		self.name, con_type, self.is_defferable, self.is_deffered, keys = row[:5]
		self.keys = map(int, keys.split(' '))
		self.con_type = TableConstraint.types[con_type]   # convert to enum
		if self.con_type == TableConstraint.TypeCheck:
			self.check_src = row[5]
		elif self.con_type == TableConstraint.TypeForeignKey:
			self.foreign_table = row[6]
			self.foreign_on_update = TableConstraint.on_action[row[7]]
			self.foreign_on_delete = TableConstraint.on_action[row[8]]
			self.foreign_match_type = TableConstraint.match_types[row[9]]
			self.foreign_keys = row[10]


class TableIndex(DbConn.TableIndex):
	def __init__(self, row):
		self.name, columns = row
		self.columns = map(int, columns.split(' '))


class TableTrigger(DbConn.TableTrigger):
	def __init__(self, row):
		self.name, self.function, self.type, self.enabled = row


class TableRule(DbConn.TableRule):
	def __init__(self, row):
		self.name, self.definition = row


class DbError(DbConn.DbError):
	def __init__(self, error, query=None):
		# save error. funny that the variables are in utf8, not 
		msg = unicode( error.args[0], 'utf-8')
		if query == None:
			if hasattr(error, "cursor") and hasattr(error.cursor, "query"):
				query = unicode(error.cursor.query, 'utf-8')
		else:
			query = unicode(query)
		DbConn.DbError.__init__(self, msg, query)
		

class TableField(DbConn.TableField):
	def __init__(self, name, data_type, is_null=None, default=None, modifier=None):
		self.name, self.data_type, self.is_null, self.default, self.modifier = name, data_type, is_null, default, modifier
		

class Connection(DbConn.Connection):

	@classmethod
	def getTypeName(self):
		return 'postgis'

	@classmethod
	def getTypeNameString(self):
		return 'PostgreSQL'

	@classmethod
	def getProviderName(self):
		return 'postgres'

	@classmethod
	def getSettingsKey(self):
		return 'PostgreSQL'

	@classmethod
	def icon(self):
		return QIcon(":/icons/postgis_elephant.png")

	@classmethod
	def connect(self, selected, parent=None):
		settings = QSettings()
		settings.beginGroup( u"/%s/connections/%s" % (self.getSettingsKey(), selected) )

		if not settings.contains( "database" ): # non-existent entry?
			raise DbError( 'there is no defined database connection "%s".' % selected )
	
		get_value_str = lambda x: unicode(settings.value(x) if Utils.isSIPv2() else settings.value(x).toString())
		service, host, port, database, username, password = map(get_value_str, ["service", "host", "port", "database", "username", "password"])

		# qgis1.5 use 'savePassword' instead of 'save' setting
		isSave = settings.value("save") if Utils.isSIPv2() else settings.value("save").toBool()
		isSavePassword = settings.value("savePassword") if Utils.isSIPv2() else settings.value("savePassword").toBool()
		if not ( isSave or isSavePassword ):
			(password, ok) = QInputDialog.getText(parent, "Enter password", 'Enter password for connection "%s":' % selected, QLineEdit.Password)
			if not ok: return

		settings.endGroup()

		uri = qgis.core.QgsDataSourceURI()
		if service:
			uri.setConnection(service, database, username, password)
		else:
			uri.setConnection(host, port, database, username, password)

		return Connection(uri)

	
	def __init__(self, uri):
		DbConn.Connection.__init__(self, uri)

		self.service = uri.service()
		self.host = uri.host()
		self.port = uri.port()
		self.dbname = uri.database()
		self.user = uri.username()
		self.passwd = uri.password()
		
		try:
			self.con = psycopg2.connect(self.con_info())
		except psycopg2.OperationalError, e:
			raise DbError(e)

		if not self.dbname:
			self.dbname = self.get_dbname()
		
		self.has_spatial = self.check_spatial()

		self.check_geometry_columns_table()

		# a counter to ensure that the cursor will be unique
		self.last_cursor_id = 0

	def con_info(self):
		con_str = ''
		if self.service: con_str += "service='%s' "  % self.service
		if self.host:    con_str += "host='%s' "     % self.host
		if self.port:    con_str += "port=%s "       % self.port
		if self.dbname:  con_str += "dbname='%s' "   % self.dbname
		if self.user:    con_str += "user='%s' "     % self.user
		if self.passwd:  con_str += "password='%s' " % self.passwd
		return con_str
	
	def get_dbname(self):
		c = self.con.cursor()
		self._exec_sql(c, "SELECT current_database()")
		return c.fetchone()[0]

	def get_info(self):
		c = self.con.cursor()
		self._exec_sql(c, "SELECT version()")
		return c.fetchone()[0]
	
	def check_spatial(self):
		""" check whether postgis_version is present in catalog """
		c = self.con.cursor()
		self._exec_sql(c, "SELECT COUNT(*) FROM pg_proc WHERE proname = 'postgis_version'")
		return (c.fetchone()[0] > 0)
	
	def get_spatial_info(self):
		""" returns tuple about postgis support:
			- lib version
			- installed scripts version
			- released scripts version
			- geos version
			- proj version
			- whether uses stats
		"""
		c = self.con.cursor()
		self._exec_sql(c, "SELECT postgis_lib_version(), postgis_scripts_installed(), postgis_scripts_released(), postgis_geos_version(), postgis_proj_version(), postgis_uses_stats()")
		return c.fetchone()
		
	def check_geometry_columns_table(self):

		c = self.con.cursor()
		self._exec_sql(c, "SELECT relname FROM pg_class WHERE relname = 'geometry_columns' AND pg_class.relkind IN ('v', 'r')")
		self.has_geometry_columns = (len(c.fetchall()) != 0)
		
		if not self.has_geometry_columns:
			self.has_geometry_columns_access = False
			return
			
		# find out whether has privileges to access geometry_columns table
		self.has_geometry_columns_access = self.get_table_privileges('geometry_columns')[0]


	def list_schemas(self):
		"""
			get list of schemas in tuples: (oid, name, owner, perms)
		"""
		c = self.con.cursor()
		sql = "SELECT oid, nspname, pg_get_userbyid(nspowner), nspacl FROM pg_namespace WHERE nspname !~ '^pg_' AND nspname != 'information_schema'"
		self._exec_sql(c, sql)

		schema_cmp = lambda x,y: -1 if x[1] < y[1] else 1
		
		return sorted(c.fetchall(), cmp=schema_cmp)
			
	def list_geotables(self, schema=None):
		"""
			get list of tables with schemas, whether user has privileges, whether table has geometry column(s) etc.
			
			geometry_columns:
			- f_table_schema
			- f_table_name
			- f_geometry_column
			- coord_dimension
			- srid
			- type
		"""
		c = self.con.cursor()
		
		if schema:
			schema_where = " AND nspname = '%s' " % self._quote_str(schema)
		else:
			schema_where = " AND (nspname != 'information_schema' AND nspname !~ 'pg_') "
			
		# LEFT OUTER JOIN: like LEFT JOIN but if there are more matches, for join, all are used (not only one)
		
		# first find out whether postgis is enabled
		if not self.has_spatial:
			# get all tables and views
			sql = """SELECT pg_class.relname, pg_namespace.nspname, pg_class.relkind, pg_get_userbyid(relowner), reltuples, relpages, NULL, NULL, NULL, NULL
							FROM pg_class
							JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace
							WHERE pg_class.relkind IN ('v', 'r')""" + schema_where + "ORDER BY nspname, relname"
		else:
			# discovery of all tables and whether they contain a geometry column
			sql = """SELECT pg_class.relname, pg_namespace.nspname, pg_class.relkind, pg_get_userbyid(relowner), reltuples, relpages, pg_attribute.attname, pg_attribute.atttypid::regtype, NULL, NULL
							FROM pg_class
							JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace
							LEFT OUTER JOIN pg_attribute ON pg_attribute.attrelid = pg_class.oid AND
									( pg_attribute.atttypid = 'geometry'::regtype
										OR pg_attribute.atttypid IN (SELECT oid FROM pg_type WHERE typbasetype='geometry'::regtype ) )
							WHERE pg_class.relkind IN ('v', 'r')""" + schema_where + "ORDER BY nspname, relname, attname"
						  
		self._exec_sql(c, sql)
		items = c.fetchall()
		
		# get geometry info from geometry_columns if exists
		if self.has_spatial and self.has_geometry_columns and self.has_geometry_columns_access:
			sql = """SELECT relname, nspname, relkind, pg_get_userbyid(relowner), reltuples, relpages,
							geometry_columns.f_geometry_column, geometry_columns.type, geometry_columns.coord_dimension, geometry_columns.srid
							FROM pg_class
						  JOIN pg_namespace ON relnamespace=pg_namespace.oid
						  LEFT OUTER JOIN geometry_columns ON relname=f_table_name AND nspname=f_table_schema
						  WHERE (relkind = 'r' or relkind='v') """ + schema_where + "ORDER BY nspname, relname, f_geometry_column"
			self._exec_sql(c, sql)
			
			# merge geometry info to "items"
			for i, geo_item in enumerate(c.fetchall()):
				if geo_item[7]:
					items[i] = geo_item
			
		return items
	
	
	def get_table_rows(self, table, schema=None):
		c = self.con.cursor()
		self._exec_sql(c, "SELECT COUNT(*) FROM %s" % self._table_name(schema, table))
		return c.fetchone()[0]
		
		
	def get_table_fields(self, table, schema=None):
		""" return list of columns in table """
		c = self.con.cursor()
		schema_where = " AND nspname='%s' " % self._quote_str(schema) if schema is not None else ""
		sql = """SELECT a.attnum AS ordinal_position,
				a.attname AS column_name,
				t.typname AS data_type,
				a.attlen AS char_max_len,
				a.atttypmod AS modifier,
				a.attnotnull AS notnull,
				a.atthasdef AS hasdefault,
				adef.adsrc AS default_value
			FROM pg_class c
			JOIN pg_attribute a ON a.attrelid = c.oid
			JOIN pg_type t ON a.atttypid = t.oid
			JOIN pg_namespace nsp ON c.relnamespace = nsp.oid
			LEFT JOIN pg_attrdef adef ON adef.adrelid = a.attrelid AND adef.adnum = a.attnum
			WHERE
			  c.relname = '%s' %s AND
				a.attnum > 0
			ORDER BY a.attnum""" % (self._quote_str(table), schema_where)

		self._exec_sql(c, sql)
		attrs = []
		for row in c.fetchall():
			attrs.append(TableAttribute(row))
		return attrs
		
		
	def get_table_indexes(self, table, schema=None):
		""" get info about table's indexes. ignore primary key and unique constraint index, they get listed in constaints """
		c = self.con.cursor()
		
		schema_where = " AND nspname='%s' " % self._quote_str(schema) if schema is not None else ""
		sql = """SELECT relname, indkey FROM pg_class, pg_index
						 WHERE pg_class.oid = pg_index.indexrelid AND pg_class.oid IN (
						         SELECT indexrelid FROM pg_index, pg_class
										 JOIN pg_namespace nsp ON pg_class.relnamespace = nsp.oid
										 WHERE pg_class.relname='%s' %s AND pg_class.oid=pg_index.indrelid
										 AND indisprimary != 't' )""" % (self._quote_str(table), schema_where) # AND indisunique != 't' 
		self._exec_sql(c, sql)
		indexes = []
		for row in c.fetchall():
			indexes.append(TableIndex(row))
		return indexes


	def get_table_unique_indexes(self, table, schema=None):
		""" get all the unique indexes """
		schema_where = " AND nspname='%s' " % self._quote_str(schema) if schema is not None else ""
		sql = """SELECT relname, indkey 
						FROM pg_index JOIN pg_class ON pg_index.indrelid=pg_class.oid 
						JOIN pg_namespace nsp ON pg_class.relnamespace = nsp.oid 
							WHERE pg_class.relname='%s' %s 
							AND indisprimary != 't' AND indisunique = 't'""" % (self._quote_str(table), schema_where)
		c = self.con.cursor()
		self._exec_sql(c, sql)
		uniqueIndexes = []
		for row in c.fetchall():
			uniqueIndexes.append(TableIndex(row))
		return uniqueIndexes
	
	
	def get_table_constraints(self, table, schema=None):
		c = self.con.cursor()
		
		schema_where = " AND nspname='%s' " % self._quote_str(schema) if schema is not None else ""
		sql = """SELECT c.conname, c.contype, c.condeferrable, c.condeferred, array_to_string(c.conkey, ' '), c.consrc,
		         t2.relname, c.confupdtype, c.confdeltype, c.confmatchtype, array_to_string(c.confkey, ' ') FROM pg_constraint c
		  LEFT JOIN pg_class t ON c.conrelid = t.oid
			LEFT JOIN pg_class t2 ON c.confrelid = t2.oid
			JOIN pg_namespace nsp ON t.relnamespace = nsp.oid
			WHERE t.relname = '%s' %s """ % (self._quote_str(table), schema_where)
		
		self._exec_sql(c, sql)
		
		constrs = []
		for row in c.fetchall():
			constrs.append(TableConstraint(row))
		return constrs


	def get_table_triggers(self, table, schema=None):
		c = self.con.cursor()
		
		schema_where = " AND nspname='%s' " % self._quote_str(schema) if schema is not None else ""
		sql = """ SELECT tgname, proname, tgtype, tgenabled FROM pg_trigger trig
		          LEFT JOIN pg_class t ON trig.tgrelid = t.oid
							LEFT JOIN pg_proc p ON trig.tgfoid = p.oid
							JOIN pg_namespace nsp ON t.relnamespace = nsp.oid
							WHERE t.relname ='%s' %s """ % (self._quote_str(table), schema_where)
	
		self._exec_sql(c, sql)

		triggers = []
		for row in c.fetchall():
			triggers.append(TableTrigger(row))
		return triggers
		
	
	def get_table_rules(self, table, schema=None):
		c = self.con.cursor()
		
		schema_where = " AND schemaname='%s' " % self._quote_str(schema) if schema is not None else ""
		sql = """ SELECT rulename, definition FROM pg_rules
					WHERE tablename='%s' %s """ % (self._quote_str(table), schema_where)
	
		self._exec_sql(c, sql)

		rules = []
		for row in c.fetchall():
			rules.append(TableRule(row))

		return rules

	def get_table_estimated_extent(self, geom, table, schema=None):
		""" find out estimated extent (from the statistics) """
		c = self.con.cursor()

		extent = "estimated_extent('%s','%s','%s')" % (self._quote_str(schema), self._quote_str(table), self._quote_str(geom))
		sql = """ SELECT xmin(%(ext)s), ymin(%(ext)s), xmax(%(ext)s), ymax(%(ext)s) """ % { 'ext' : extent }
		self._exec_sql(c, sql)
		
		row = c.fetchone()
		return row
	
	def get_view_definition(self, view, schema=None):
		""" returns definition of the view """
		schema_where = " AND nspname='%s' " % self._quote_str(schema) if schema is not None else ""
		sql = """SELECT pg_get_viewdef(c.oid) FROM pg_class c
						JOIN pg_namespace nsp ON c.relnamespace = nsp.oid
		        WHERE relname='%s' %s AND relkind='v'""" % (self._quote_str(view), schema_where)
		c = self.con.cursor()
		self._exec_sql(c, sql)
		return c.fetchone()[0]
		
	"""
	def list_tables(self):
		c = self.con.cursor()
		c.execute("SELECT relname FROM pg_class WHERE relname !~ '^(pg_|sql_)' AND relkind = 'r'")
		return c.fetchall()
	"""
		
	def add_geometry_column(self, table, geom_type, schema=None, geom_column='the_geom', srid=-1, dim=2):
		
		# use schema if explicitly specified
		if schema:
			schema_part = "'%s', " % self._quote_str(schema)
		else:
			schema_part = ""
		sql = "SELECT AddGeometryColumn(%s'%s', '%s', %d, '%s', %d)" % (schema_part, self._quote_str(table), self._quote_str(geom_column), srid, self._quote_str(geom_type), dim)
		self._exec_sql_and_commit(sql)
		
	def delete_geometry_column(self, table, geom_column, schema=None):
		""" use postgis function to delete geometry column correctly """
		if schema:
			schema_part = "'%s', " % self._quote_str(schema)
		else:
			schema_part = ""
		sql = "SELECT DropGeometryColumn(%s'%s', '%s')" % (schema_part, self._quote_str(table), self._quote_str(geom_column))
		self._exec_sql_and_commit(sql)
		
	def delete_geometry_table(self, table, schema=None):
		""" delete table with one or more geometries using postgis function """
		if schema:
			schema_part = "'%s', " % self._quote_str(schema)
		else:
			schema_part = ""
		sql = "SELECT DropGeometryTable(%s'%s')" % (schema_part, self._quote_str(table))
		self._exec_sql_and_commit(sql)
		
	def create_table(self, table, fields, pkey=None, schema=None):
		""" create ordinary table
				'fields' is array containing instances of TableField
				'pkey' contains name of column to be used as primary key
		"""
				
		if len(fields) == 0:
			return False
		
		table_name = self._table_name(schema, table)
		
		sql = "CREATE TABLE %s (%s" % (table_name, fields[0].field_def(self))
		for field in fields[1:]:
			sql += ", %s" % field.field_def(self)
		if pkey:
			sql += ", PRIMARY KEY (%s)" % self._quote(pkey)
		sql += ")"
		self._exec_sql_and_commit(sql)
		return True
	
	def delete_table(self, table, schema=None):
		""" delete table from the database """
		table_name = self._table_name(schema, table)
		sql = "DROP TABLE %s" % table_name
		self._exec_sql_and_commit(sql)
		
	def empty_table(self, table, schema=None):
		""" delete all rows from table """
		table_name = self._table_name(schema, table)
		sql = "TRUNCATE %s" % table_name
		self._exec_sql_and_commit(sql)
		
	def rename_table(self, table, new_table, schema=None):
		""" rename a table in database """
		table_name = self._table_name(schema, table)
		sql = "ALTER TABLE %s RENAME TO %s" % (table_name, self._quote(new_table))
		self._exec_sql_and_commit(sql)
		
		# update geometry_columns if postgis is enabled
		if self.has_spatial and self.has_geometry_columns and self.has_geometry_columns_access:
			sql = "UPDATE geometry_columns SET f_table_name='%s' WHERE f_table_name='%s'" % (self._quote_str(new_table), self._quote_str(table))
			if schema is not None:
				sql += " AND f_table_schema='%s'" % self._quote_str(schema)
			self._exec_sql_and_commit(sql)
		
	def create_view(self, name, query, schema=None):
		view_name = self._table_name(schema, name)
		sql = "CREATE VIEW %s AS %s" % (view_name, query)
		self._exec_sql_and_commit(sql)
	
	def delete_view(self, name, schema=None):
		view_name = self._table_name(schema, name)
		sql = "DROP VIEW %s" % view_name
		self._exec_sql_and_commit(sql)
	
	def rename_view(self, name, new_name, schema=None):
		""" rename view in database """
		self.rename_table(name, new_name, schema)
		
	def create_schema(self, schema):
		""" create a new empty schema in database """
		sql = "CREATE SCHEMA %s" % self._quote(schema)
		self._exec_sql_and_commit(sql)
		
	def delete_schema(self, schema):
		""" drop (empty) schema from database """
		sql = "DROP SCHEMA %s" % self._quote(schema)
		self._exec_sql_and_commit(sql)
		
	def rename_schema(self, schema, new_schema):
		""" rename a schema in database """
		sql = "ALTER SCHEMA %s RENAME TO %s" % (self._quote(schema), self._quote(new_schema))
		self._exec_sql_and_commit(sql)
		
		# update geometry_columns if postgis is enabled
		if self.has_spatial:
			sql = "UPDATE geometry_columns SET f_table_schema='%s' WHERE f_table_schema='%s'" % (self._quote_str(new_schema), self._quote_str(schema)) 
			self._exec_sql_and_commit(sql)
		
	def table_add_column(self, table, field, schema=None):
		""" add a column to table (passed as TableField instance) """
		table_name = self._table_name(schema, table)
		sql = "ALTER TABLE %s ADD %s" % (table_name, field.field_def(self))
		self._exec_sql_and_commit(sql)
		
	def table_delete_column(self, table, field, schema=None):
		""" delete column from a table """
		table_name = self._table_name(schema, table)
		sql = "ALTER TABLE %s DROP %s" % (table_name, self._quote(field))
		self._exec_sql_and_commit(sql)
		
	def table_column_rename(self, table, name, new_name, schema=None):
		""" rename column in a table """
		table_name = self._table_name(schema, table)
		sql = "ALTER TABLE %s RENAME %s TO %s" % (table_name, self._quote(name), self._quote(new_name))
		self._exec_sql_and_commit(sql)
		
		# update geometry_columns if postgis is enabled
		if self.has_spatial:
			sql = "UPDATE geometry_columns SET f_geometry_column='%s' WHERE f_geometry_column='%s' AND f_table_name='%s'" % (self._quote_str(new_name), self._quote_str(name), self._quote_str(table))
			if schema is not None:
				sql += " AND f_table_schema='%s'" % self._quote(schema)
			self._exec_sql_and_commit(sql)

	def table_column_set_type(self, table, column, data_type, schema=None):
		""" change column type """
		table_name = self._table_name(schema, table)
		sql = "ALTER TABLE %s ALTER %s TYPE %s" % (table_name, self._quote(column), data_type)
		self._exec_sql_and_commit(sql)
		
	def table_column_set_default(self, table, column, default, schema=None):
		""" change column's default value. If default=None drop default value """
		table_name = self._table_name(schema, table)
		if default:
			sql = "ALTER TABLE %s ALTER %s SET DEFAULT %s" % (table_name, self._quote(column), default)
		else:
			sql = "ALTER TABLE %s ALTER %s DROP DEFAULT" % (table_name, self._quote(column))
		self._exec_sql_and_commit(sql)
		
	def table_column_set_null(self, table, column, is_null, schema=None):
		""" change whether column can contain null values """
		table_name = self._table_name(schema, table)
		sql = "ALTER TABLE %s ALTER %s " % (table_name, self._quote(column))
		if is_null:
			sql += "DROP NOT NULL"
		else:
			sql += "SET NOT NULL"
		self._exec_sql_and_commit(sql)
		
	def table_add_primary_key(self, table, column, schema=None):
		""" add a primery key (with one column) to a table """
		table_name = self._table_name(schema, table)
		sql = "ALTER TABLE %s ADD PRIMARY KEY (%s)" % (table_name, self._quote(column))
		self._exec_sql_and_commit(sql)
		
	def table_add_unique_constraint(self, table, column, schema=None):
		""" add a unique constraint to a table """
		table_name = self._table_name(schema, table)
		sql = "ALTER TABLE %s ADD UNIQUE (%s)" % (table_name, self._quote(column))
		self._exec_sql_and_commit(sql)
	
	def table_delete_constraint(self, table, constraint, schema=None):
		""" delete constraint in a table """
		table_name = self._table_name(schema, table)
		sql = "ALTER TABLE %s DROP CONSTRAINT %s" % (table_name, self._quote(constraint))
		self._exec_sql_and_commit(sql)
		
	def table_move_to_schema(self, table, new_schema, schema=None):
		if new_schema == schema:
			return
		table_name = self._table_name(schema, table)
		sql = "ALTER TABLE %s SET SCHEMA %s" % (table_name, self._quote(new_schema))
		self._exec_sql_and_commit(sql)
		
		# update geometry_columns if postgis is enabled
		if self.has_spatial:
			sql = "UPDATE geometry_columns SET f_table_schema='%s' WHERE f_table_name='%s'" % (self._quote_str(new_schema), self._quote_str(table))
			if schema is not None:
				sql += " AND f_table_schema='%s'" % self._quote_str(schema)
			self._exec_sql_and_commit(sql)

	def table_apply_function(self, schema, table, res_column, fct, param):
		""" apply a function to a column and save the result in other column """
		table = self._table_name(schema, table)
		sql = "UPDATE %s SET %s = %s(%s)" % (table, self._quote(res_column), fct, self._quote(param))
		self._exec_sql_and_commit(sql)
		
	def table_enable_triggers(self, table, schema, enable=True):
		""" enable or disable all triggers on table """
		table = self._table_name(schema, table)
		sql = "ALTER TABLE %s %s TRIGGER ALL" % (table, "ENABLE" if enable else "DISABLE")
		self._exec_sql_and_commit(sql)
		
	def table_enable_trigger(self, table, schema, trigger, enable=True):
		""" enable or disable one trigger on table """
		table = self._table_name(schema, table)
		sql = "ALTER TABLE %s %s TRIGGER %s" % (table, "ENABLE" if enable else "DISABLE", self._quote(trigger))
		self._exec_sql_and_commit(sql)
		
	def table_delete_trigger(self, table, schema, trigger):
		""" delete trigger on table """
		table = self._table_name(schema, table)
		sql = "DROP TRIGGER %s ON %s" % (self._quote(trigger), table)
		self._exec_sql_and_commit(sql)

	def table_delete_rule(self, table, schema, rule):
		""" delete rule on table """
		table = self._table_name(schema, table)
		sql = "DROP RULE %s ON %s" % (self._quote(rule), table)
		self._exec_sql_and_commit(sql)

	def create_index(self, table, name, column, schema=None):
		""" create index on one column using default options """
		table_name = self._table_name(schema, table)
		idx_name = self._quote(name)
		sql = "CREATE INDEX %s ON %s (%s)" % (idx_name, table_name, self._quote(column))
		self._exec_sql_and_commit(sql)
	
	def create_spatial_index(self, table, schema=None, geom_column='the_geom'):
		table_name = self._table_name(schema, table)
		idx_name = self._quote("sidx_"+table)
		sql = "CREATE INDEX %s ON %s USING GIST(%s)" % (idx_name, table_name, self._quote(geom_column))
		self._exec_sql_and_commit(sql)
		
	def delete_index(self, name, schema=None):
		index_name = self._table_name(schema, name)
		sql = "DROP INDEX %s" % index_name
		self._exec_sql_and_commit(sql)
		
	def get_database_privileges(self):
		""" db privileges: (can create schemas, can create temp. tables) """
		sql = "SELECT has_database_privilege('%(d)s', 'CREATE'), has_database_privilege('%(d)s', 'TEMP')" % { 'd' : self._quote_str(self.dbname) }
		c = self.con.cursor()
		self._exec_sql(c, sql)
		return c.fetchone()
		
	def get_schema_privileges(self, schema):
		""" schema privileges: (can create new objects, can access objects in schema) """
		sql = "SELECT has_schema_privilege('%(s)s', 'CREATE'), has_schema_privilege('%(s)s', 'USAGE')" % { 's' : self._quote_str(schema) }
		c = self.con.cursor()
		self._exec_sql(c, sql)
		return c.fetchone()
	
	def get_table_privileges(self, table, schema=None):
		""" table privileges: (select, insert, update, delete) """
		t = self._table_name(schema, table)
		sql = """SELECT has_table_privilege('%(t)s', 'SELECT'), has_table_privilege('%(t)s', 'INSERT'),
		                has_table_privilege('%(t)s', 'UPDATE'), has_table_privilege('%(t)s', 'DELETE')""" % { 't': self._quote_str(t) }
		c = self.con.cursor()
		self._exec_sql(c, sql)
		return c.fetchone()
	
	def vacuum_analyze(self, table, schema=None):
		""" run vacuum analyze on a table """
		t = self._table_name(schema, table)
		# vacuum analyze must be run outside transaction block - we have to change isolation level
		self.con.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
		c = self.con.cursor()
		self._exec_sql(c, "VACUUM ANALYZE %s" % t)
		self.con.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_READ_COMMITTED)
		
	def sr_info_for_srid(self, srid):
		if not self.has_spatial:
			return "Unknown"
		
		try:
			c = self.con.cursor()
			self._exec_sql(c, "SELECT srtext FROM spatial_ref_sys WHERE srid = '%d'" % srid)
			sr = c.fetchone()
			if sr is None:
				return "Unknown"
			srtext = sr[0]
			# try to extract just SR name (should be qouted in double quotes)
			x = re.search('"([^"]+)"', srtext)
			if x is not None:
				srtext = x.group()
			return srtext
		except DbError, e:
			return "Unknown"
	
	def insert_table_row(self, table, values, schema=None, cursor=None):
		""" insert a row with specified values to a table.
		 if a cursor is specified, it doesn't commit (expecting that there will be more inserts)
		 otherwise it commits immediately """
		t = self._table_name(schema, table)
		sql = ""
		for value in values:
			# TODO: quote values?
			if sql: sql += ", "
			sql += value
		sql = "INSERT INTO %s VALUES (%s)" % (t, sql)
		if cursor:
			self._exec_sql(cursor, sql)
		else:
			self._exec_sql_and_commit(sql)


	def table_add_function_trigger(self, schema, table, resColumn, fct, geomColumn):
		""" add a trigger on insert and update that recalculates the value from geometry column """
		
		trig_f_name = "%s_calc_%s" % (table, fct)
		trig_name = "calc_%s" % fct
		ctx = { 'fname' : trig_f_name, 'tname' : trig_name,
		        'res' : resColumn, 'geom' : geomColumn,
						'f' : fct, 'table' : self._table_name(schema, table) }
		sql = """
			CREATE OR REPLACE FUNCTION %(fname)s() RETURNS TRIGGER AS
			$$
			BEGIN
				IF (TG_OP = 'INSERT') THEN
					NEW.%(res)s := %(f)s(NEW.%(geom)s);
				ELSIF (TG_OP = 'UPDATE') THEN
					IF NOT (NEW.%(geom)s ~= OLD.%(geom)s) THEN
						NEW.%(res)s := %(f)s(NEW.%(geom)s);
					END IF;
				END IF;
			RETURN NEW;
			END;
			$$
			LANGUAGE 'plpgsql';

			CREATE TRIGGER %(tname)s BEFORE INSERT OR UPDATE ON %(table)s FOR EACH ROW
			EXECUTE PROCEDURE %(fname)s();
		""" % ctx
		
		self._exec_sql_and_commit(sql)


	def get_named_cursor(self, table=None):
		""" return an unique named cursor, optionally including a table name """
		self.last_cursor_id += 1
		if table is not None:
			table2 = re.sub(r'\W', '_', table.encode('ascii','replace')) # all non-alphanum characters to underscore
			cur_name = "cursor_%d_table_%s" % (self.last_cursor_id, table2)
		else:
			cur_name = "cursor_%d" % self.last_cursor_id
		#cur_name = ("\"db_table_"+self.table+"\"").replace(' ', '_')
		#cur_name = cur_name.encode('ascii','replace').replace('?', '_')
		return self.con.cursor(cur_name)
		
	def _exec_sql(self, cursor, sql):
		try:
			cursor.execute(sql)
		except psycopg2.Error, e:
			# do the rollback to avoid a "current transaction aborted, commands ignored" errors
			self.con.rollback()
			raise DbError(e)
		
	def _exec_sql_and_commit(self, sql):
		""" tries to execute and commit some action, on error it rolls back the change """
		#try:
		c = self.con.cursor()
		self._exec_sql(c, sql)
		self.con.commit()
		#except DbError, e:
		#	self.con.rollback()
		#	raise

	def _quote(self, identifier):
		identifier = unicode(identifier) # make sure it's python unicode string
		return u'"%s"' % identifier.replace('"', '""')
	
	def _quote_str(self, txt):
		""" make the string safe - replace ' with '' """
		txt = unicode(txt) # make sure it's python unicode string
		return txt.replace("'", "''")
		
	def _table_name(self, schema, table):
		if not schema:
			return self._quote(table)
		else:
			return u"%s.%s" % (self._quote(schema), self._quote(table))
		

# for debugging / testing
if __name__ == '__main__':

	db = GeoDB(host='localhost',dbname='gis',user='gisak',passwd='g')
	
	print db.list_schemas()
	print '=========='
	
	for row in db.list_geotables():
		print row

	print '=========='
	
	for row in db.get_table_indexes('trencin'):
		print row

	print '=========='
	
	for row in db.get_table_constraints('trencin'):
		print row
	
	print '=========='
	
	print db.get_table_rows('trencin')
	
	#for fld in db.get_table_metadata('trencin'):
	#	print fld
	
	#try:
	#	db.create_table('trrrr', [('id','serial'), ('test','text')])
	#except DbError, e:
	#	print e.message, e.query
	
# vim: noet ts=8 :
