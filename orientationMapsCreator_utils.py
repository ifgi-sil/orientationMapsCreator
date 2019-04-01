# -*- coding: utf-8 -*-

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from qgis.core import *
from qgis.gui import *
import psycopg2
import sip
import os
import io
import chardet
import codecs


# def getSridAndGeomType(con, table, geometry):
#     args = {}
#     args['table'] = table
#     args['geometry'] = geometry
#     cur = con.cursor()
#     cur.execute("""
#         SELECT ST_SRID(%(geometry)s), ST_GeometryType(%(geometry)s)
#             FROM %(table)s 
#             LIMIT 1
#     """ % args)
#     row = cur.fetchone()
#     return row[0], row[1]

def getSridAndGeomType(con, args):
    cur = con.cursor()
    cur.execute("""
        SELECT ST_SRID(%(geometry)s), ST_GeometryType(%(geometry)s)
            FROM %(edge_schema)s.%(edge_table)s 
            LIMIT 1
    """ % args)
    row = cur.fetchone()
    return row[0], row[1]

def setStartPoint(geomType, args):
    if geomType == 'ST_MultiLineString':
        args['startpoint'] = "ST_StartPoint(ST_GeometryN(%(geometry)s, 1))" % args
    elif geomType == 'ST_LineString':
        args['startpoint'] = "ST_StartPoint(%(geometry)s)" % args

def setEndPoint(geomType, args):
    if geomType == 'ST_MultiLineString':
        args['endpoint'] = "ST_EndPoint(ST_GeometryN(%(geometry)s, 1))" % args
    elif geomType == 'ST_LineString':
        args['endpoint'] = "ST_EndPoint(%(geometry)s)" % args

def setTransformQuotes(args, srid, canvas_srid):
    if srid > 0 and canvas_srid > 0:
        args['transform_s'] = "ST_Transform("
        args['transform_e'] = ", %(canvas_srid)d)" % args
    else:
        args['transform_s'] = ""
        args['transform_e'] = ""

def isSIPv2():
    return sip.getapi('QVariant') > 1

def getStringValue(settings, key, value):
    if isSIPv2():
        return settings.value(key, value, type=str)
    else:
        return settings.value(key, QVariant(value)).toString()

def getBoolValue(settings, key, value):
    if isSIPv2():
        return settings.value(key, value, type=bool)
    else:
        return settings.value(key, QVariant(value)).toBool()

def isQGISv1():
    return QGis.QGIS_VERSION_INT < 10900

def getDestinationCrs(mapCanvas):
    if isQGISv1():
        return mapCanvas.mapRenderer().destinationSrs()
    else:
        if QGis.QGIS_VERSION_INT < 20400:
            return mapCanvas.mapRenderer().destinationCrs()
        else:
            return mapCanvas.mapSettings().destinationCrs()

def getCanvasSrid(crs):
    if isQGISv1():
        return crs.epsg()
    else:
        return crs.postgisSrid()

def createFromSrid(crs, srid):
    if isQGISv1():
        return crs.createFromEpsg(srid)
    else:
        return crs.createFromSrid(srid)

def getRubberBandType(isPolygon):
    if isQGISv1():
        return isPolygon
    else:
        if isPolygon:
            return QGis.Polygon
        else:
            return QGis.Line

def refreshMapCanvas(mapCanvas):
    if QGis.QGIS_VERSION_INT < 20400:
        return mapCanvas.clear()
    else:
        return mapCanvas.refresh()

def logMessage(message, level=QgsMessageLog.INFO):
    QgsMessageLog.logMessage(message, 'pgRouting Layer', level)

def getNodeQuery(args, geomType):
    setStartPoint(geomType, args)
    setEndPoint(geomType, args)
    return """
        WITH node AS (
            SELECT id::int4,
                ST_X(%(geometry)s) AS x,
                ST_Y(%(geometry)s) AS y,
                %(geometry)s
                FROM (
                    SELECT %(source)s::int4 AS id,
                        %(startpoint)s AS %(geometry)s
                        FROM %(edge_schema)s.%(edge_table)s
                    UNION
                    SELECT %(target)s::int4 AS id,
                        %(endpoint)s AS %(geometry)s
                        FROM %(edge_schema)s.%(edge_table)s
                ) AS node
        )""" % args

def getPgrVersion(con):
    try:
        cur = con.cursor()
        cur.execute('SELECT version FROM pgr_version()')
        row = cur.fetchone()[0]
        versions =  ''.join([i for i in row if i.isdigit()])
        version = versions[0]
        if versions[1]:
            version += '.' + versions[1]
        return float(version)
    except psycopg2.DatabaseError, e:
        #database didn't have pgrouting
        return 0;
    except SystemError, e:
        return 0
    
def readFile(rel_path):
    
    plugin_dir = os.path.dirname(__file__)
    rel_path = os.path.join(plugin_dir, rel_path)
    
    #make sure to load file without BOM mark
    bytes = min(32, os.path.getsize(rel_path))
    raw = open(rel_path, 'rb').read(bytes)

    if raw.startswith(codecs.BOM_UTF8):
        encoding = 'utf-8-sig'
    else:
        result = chardet.detect(raw)
        encoding = result['encoding']
    
    filehandle = io.open(rel_path, encoding=encoding)
    file = filehandle.read()
    filehandle.close()
    
    return file

def getMissingFktQuery(fkt):    
    print "** getMissingFkt"
    
    if (fkt == "my_route_length_buffer"):
        sqlFile = readFile("assets/sql_functions/my_route_length_buffer.sql")
    elif (fkt == "my_route_get_dp"):
        sqlFile = readFile("assets/sql_functions/my_route_get_dp.sql")
    elif (fkt == "my_regions_route_intersect_buffer"):
        sqlFile = readFile("assets/sql_functions/my_regions_route_intersect_buffer.sql")
    elif (fkt == "my_admin_regions_route_intersect_buffer"):
        sqlFile = readFile("assets/sql_functions/my_admin_regions_route_intersect_buffer.sql")
    else:
        sqlFile = ""
    
    return sqlFile



