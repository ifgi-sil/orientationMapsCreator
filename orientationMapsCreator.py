# -*- coding: utf-8 -*-

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from qgis.core import *
from qgis.gui import *
from orientationMapsCreator_dockwidget import orientationMapsCreatorDockWidget
import orientationMapsCreator_utils as Utils
import dbConnection
import os
import psycopg2     #DatabaseError
import re           #RegularExpressions
import glob


# Initialize Qt resources from file resources.py
import resources
from qgis._core import QgsVectorLayer

conn = dbConnection.ConnectionManager()

class orientationMapsCreator:
    """QGIS Plugin Implementation."""
    
    SUPPORTED_FUNCTIONS = [
        'dijkstra']
    
    EDGES_COLUMN_CONTROLS = [       #replace with commonControls, commonBoxes and getControlNames() from functions
            'lblGeometryColumn',    'lineEditGeometryColumn',
            'lblIDColumn',          'lineEditIDColumn',
            'lblSourceColumn',      'lineEditSourceColumn',
            'lblTargetColumn',      'lineEditTargetColumn',
            'lblCostColumn',        'lineEditCostColumn',
            'lblReverseCostColumn', 'lineEditReverseCostColumn']
    

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgisInterface
        """
        
        print "** _init_"    # this is executed when the QGIS/plugin is loaded
        
        # Save reference to the QGIS interface
        self.iface = iface
        
        # Init markers for route calculation
        self.idsVertexMarkers = []
        self.targetIdsVertexMarkers = []
        self.sourceIdsVertexMarkers = []
        self.sourceIdVertexMarker = QgsVertexMarker(self.iface.mapCanvas())
        self.sourceIdVertexMarker.setColor(Qt.blue)
        self.sourceIdVertexMarker.setPenWidth(2)
        self.sourceIdVertexMarker.setVisible(False)
        self.targetIdVertexMarker = QgsVertexMarker(self.iface.mapCanvas())
        self.targetIdVertexMarker.setColor(Qt.green)
        self.targetIdVertexMarker.setPenWidth(2)
        self.targetIdVertexMarker.setVisible(False)
        self.idsRubberBands = []
        self.sourceIdRubberBand = QgsRubberBand(self.iface.mapCanvas(), Utils.getRubberBandType(False))
        self.sourceIdRubberBand.setColor(Qt.cyan)
        self.sourceIdRubberBand.setWidth(4)
        self.targetIdRubberBand = QgsRubberBand(self.iface.mapCanvas(), Utils.getRubberBandType(False))
        self.targetIdRubberBand.setColor(Qt.yellow)
        self.targetIdRubberBand.setWidth(4)
        
        #Items drawn on the canvas without saving to a layer
        self.canvasItemList = {}
        self.canvasItemList['markers'] = []
        self.canvasItemList['annotations'] = []
        self.canvasItemList['paths'] = []
        resultPathRubberBand = QgsRubberBand(self.iface.mapCanvas(), Utils.getRubberBandType(False))
        resultPathRubberBand.setColor(QColor(255, 0, 0, 128))
        resultPathRubberBand.setWidth(4)
        self.canvasItemList['path'] = resultPathRubberBand
        resultAreaRubberBand = QgsRubberBand(self.iface.mapCanvas(), Utils.getRubberBandType(True))
        resultAreaRubberBand.setColor(Qt.magenta)
        resultAreaRubberBand.setWidth(2)
        if not Utils.isQGISv1():
            resultAreaRubberBand.setBrushStyle(Qt.Dense4Pattern)
        self.canvasItemList['area'] = resultAreaRubberBand
        
        #Layers added to the project
        self.projectLayerList = {}  
        
        #DB-Schema List
        self.dbSchemaSettings = {}
        self.dbEdgesTableSettings = {}
        self.dbVerticesTableSettings = {}

        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)

        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'orientationMapsCreator_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)

            if qVersion() > '4.3.3':
                QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&Orientation Maps Creator')
        # TODO: We are going to let the user set this up in a future iteration
        self.toolbar = self.iface.addToolBar(u'orientationMapsCreator')
        self.toolbar.setObjectName(u'orientationMapsCreator')

        print "** INITIALIZING orientationMapsCreator"

        self.pluginIsActive = False
        self.dockwidget = None


    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('orientationMapsCreator', message)


    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.toolbar.addAction(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""
        
        print "** initGui"   # this is executed when the QGIS/plugin is loaded
        
        icon_path = ':/plugins/orientationMapsCreator/icon.png'
        self.add_action(
            icon_path,
            text=self.tr(u'Orientation Maps Creator'),
            callback=self.run,
            parent=self.iface.mainWindow())
         
        if self.dockwidget == None:
            # Create the dockwidget (after translation) and keep reference
            self.dockwidget = orientationMapsCreatorDockWidget()
                 
        # connect UI actions to methods
        QObject.connect(self.dockwidget.btnLoadDefaults, SIGNAL("clicked()"), self.loadDefaultConnections)
        QObject.connect(self.dockwidget.btnDatabaseRefresh, SIGNAL("clicked()"), self.reloadConnections)
        
        QObject.connect(self.dockwidget.comboBoxDatabase, SIGNAL("currentIndexChanged(const QString&)"), self.updateDatabaseConnectionEnabled)
        QObject.connect(self.dockwidget.comboBoxEdgesSchema, SIGNAL("currentIndexChanged(const QString&)"), self.updateEdgesSchemaIndexChanged)
        QObject.connect(self.dockwidget.comboBoxEdgesTable, SIGNAL("currentIndexChanged(const QString&)"), self.updateEdgesTableIndexChanged)
        QObject.connect(self.dockwidget.comboBoxVerticesTable, SIGNAL("currentIndexChanged(const QString&)"), self.updateVerticesTableIndexChanged)
        
        QObject.connect(self.dockwidget.btnPreviewRoute, SIGNAL("clicked()"), self.previewRoute)
        QObject.connect(self.dockwidget.btnClearPreview, SIGNAL("clicked()"), self.clearPreview)
        QObject.connect(self.dockwidget.btnSaveRoute, SIGNAL("clicked()"), self.saveRoute)
        QObject.connect(self.dockwidget.btnRemoveRoute, SIGNAL("clicked()"), self.removeRoute)
         
        self.functions = {}     #Route Calculation Functions: here only dijkstra
        for funcfname in self.SUPPORTED_FUNCTIONS:
            # import the function
            exec("from functions import %s as function" % funcfname)
            funcname = function.Function.getName()
            self.functions[funcname] = function.Function(self.dockwidget)
            
        #populate the combo with connections
        self.reloadMessage = False
        self.reloadConnections()
        self.loadSettings()
        #Utils.logMessage("startup version " + str(self.version))
        self.reloadMessage = True
        
        
    #--------------------------------------------------------------------------

    def onClosePlugin(self):
        """Cleanup necessary items here when plugin dockwidget is closed"""

        print "** CLOSING orientationMapsCreator"

        # disconnects
        self.dockwidget.closingPlugin.disconnect(self.onClosePlugin)

        # remove this statement if dockwidget is to remain
        # for reuse if plugin is reopened
        # Commented next statement since it causes QGIS crashe
        # when closing the docked window:
        # self.dockwidget = None

        self.pluginIsActive = False


    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""

        print "** UNLOAD orientationMapsCreator"

        self.clearPreview()
        self.saveSettings()
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&Orientation Maps Creator'),
                action)
            self.iface.removeToolBarIcon(action)
        # remove the toolbar
        del self.toolbar
    
    
    def loadDefaultConnections(self):
        """Load Default connection parameter"""
        
        print "** loadDefaultConnections"
        #TODO
        
        function = self.functions['dijkstra']
        self.setDefaultArguments(function.getControlNames(self.version))
        
        
        
    def reloadConnections(self):
        """Reload connection to Database"""
        
        #print "** reloadConnections"

        oldReloadMessage = self.reloadMessage
        self.reloadMessage = False
        database = str(self.dockwidget.comboBoxDatabase.currentText())
        
        self.dockwidget.comboBoxDatabase.clear()
        
        connections = conn.getAvailableConnections()       #here: gets postgis connection from the postgis connector
        self.connectionsDB = {}
        for a in connections:
            self.connectionsDB[ unicode(a.text()) ] = a     #here: postgis databases

        for dbname in self.connectionsDB:
            db = None
            try:
                db = self.connectionsDB[dbname].connect()
                con = db.con
                version = Utils.getPgrVersion(con)          #version of the particular connection
                if (Utils.getPgrVersion(con) != 0):
                    self.dockwidget.comboBoxDatabase.addItem(dbname)

            except dbConnection.DbError, e:
                Utils.logMessage("dbname:" + dbname + ", " + e.msg)

            finally:
                if db and db.con:
                    db.con.close()                          #database connection is close again
                    
        #restore previously selected database if exists
        idx = self.dockwidget.comboBoxDatabase.findText(database)
        if idx >= 0:
            self.dockwidget.comboBoxDatabase.setCurrentIndex(idx) #reset to previous selection
        else:
            self.dockwidget.comboBoxDatabase.setCurrentIndex(0)

        self.reloadMessage = oldReloadMessage
        #self.updateDatabaseConnectionEnabled()
        
        
    def updateDatabaseConnectionEnabled(self):
        """Connect to selected Database"""

        #print "** updateDatabaseConnectionEnabled"
        
        dbname = str(self.dockwidget.comboBoxDatabase.currentText())
        if dbname =='':
            return

        db = self.connectionsDB[dbname].connect()
        con = db.con
        self.version = Utils.getPgrVersion(con)     #save overall version of selected database connection
#         if self.reloadMessage:
#             QMessageBox.information(self.dockwidget, self.dockwidget.windowTitle(), 
#                                     'Selected database: ' + dbname + '\npgRouting version: ' + str(self.version))
            
        self.reloadDatabaseConnectionSchemas()


    def reloadDatabaseConnectionSchemas(self):
        """Reload Schemas of connected Database"""

        #print "** reloadDatabaseConnectionSchemas"
        
        dbname = str(self.dockwidget.comboBoxDatabase.currentText())
        if dbname =='':
            return
        
        curSchema = ''
        if dbname in self.dbSchemaSettings:
            curSchema = self.dbSchemaSettings[dbname]

        self.dockwidget.comboBoxEdgesSchema.clear()
    
        try:
            db = self.connectionsDB[dbname].connect()
            con = db.con           
            for schema in db.list_schemas():
                self.dockwidget.comboBoxEdgesSchema.addItem(schema[1])
                #print "** schema = ", schema[1]
                
        except dbConnection.DbError, e:
            Utils.logMessage("dbname:" + dbname + ", " + e.msg)

        finally:
            if db and db.con:
                db.con.close()
                
        #restore previously selected schema if exists
        idx = self.dockwidget.comboBoxEdgesSchema.findText(curSchema)
        if idx >= 0:
            self.dockwidget.comboBoxEdgesSchema.setCurrentIndex(idx) #reset to previous selection
        else:
            self.dockwidget.comboBoxEdgesSchema.setCurrentIndex(0)
            
        self.dbSchemaSettings[dbname] = str(self.dockwidget.comboBoxEdgesSchema.currentText())

        self.updateEdgesSchemaIndexChanged()

    
    def updateEdgesSchemaIndexChanged(self):
        """Reload Tables of connected Schema"""

        #print "** updateEdgesSchemaIndexChanged"
        
        dbname = str(self.dockwidget.comboBoxDatabase.currentText())
        if dbname =='':
            return
        
        schema = str(self.dockwidget.comboBoxEdgesSchema.currentText())
        self.dbSchemaSettings[dbname] = schema
        
        curEdgesTable = ''
        if dbname+'.'+schema in self.dbEdgesTableSettings:
            curEdgesTable = self.dbEdgesTableSettings[dbname+'.'+schema]
            
        curVerticesTable = ''
        if dbname+'.'+schema in self.dbVerticesTableSettings:
            curVerticesTable = self.dbVerticesTableSettings[dbname+'.'+schema]
        
        self.dockwidget.comboBoxEdgesTable.clear()
        self.dockwidget.comboBoxVerticesTable.clear()
        
        try:
            db = self.connectionsDB[dbname].connect()
            con = db.con
            for table in db.list_geotables(schema):
                self.dockwidget.comboBoxEdgesTable.addItem(table[0])
                self.dockwidget.comboBoxVerticesTable.addItem(table[0])
                #print "** edgesVerticesTable = ", table[0]
                
        except dbConnection.DbError, e:
            Utils.logMessage("dbname:" + dbname + ", " + e.msg)

        finally:
            if db and db.con:
                db.con.close()
                
        #restore previously selected edges table if exists
        idx = self.dockwidget.comboBoxEdgesTable.findText(curEdgesTable)
        if idx >= 0:
            self.dockwidget.comboBoxEdgesTable.setCurrentIndex(idx) #reset to previous selection
        else:
            self.dockwidget.comboBoxEdgesTable.setCurrentIndex(0)   
        self.dbEdgesTableSettings[dbname+'.'+schema] = str(self.dockwidget.comboBoxEdgesTable.currentText())
        
        #restore previously selected edges table if exists
        idx = self.dockwidget.comboBoxVerticesTable.findText(curVerticesTable)
        if idx >= 0:
            self.dockwidget.comboBoxVerticesTable.setCurrentIndex(idx) #reset to previous selection
        else:
            self.dockwidget.comboBoxVerticesTable.setCurrentIndex(0)    
        self.dbVerticesTableSettings[dbname+'.'+schema] = str(self.dockwidget.comboBoxVerticesTable.currentText())


    def updateEdgesTableIndexChanged(self):
 
        #print "** updateEdgesTableIndexChanged"
        
        dbname = str(self.dockwidget.comboBoxDatabase.currentText())        
        schema = str(self.dockwidget.comboBoxEdgesSchema.currentText())
        table = str(self.dockwidget.comboBoxEdgesTable.currentText())
        self.dbEdgesTableSettings[dbname+'.'+schema] = table
 
         
    def updateVerticesTableIndexChanged(self):
 
        #print "** updateVerticesTableIndexChanged"
        
        dbname = str(self.dockwidget.comboBoxDatabase.currentText())        
        schema = str(self.dockwidget.comboBoxEdgesSchema.currentText())
        table = str(self.dockwidget.comboBoxVerticesTable.currentText())
        self.dbVerticesTableSettings[dbname+'.'+schema] = table
        
    
    def previewRoute(self):
        """Calculate Route from specified source to target using default postgis dijkstra function.
        
        Previews Route.
        """

        print "** previewRoute"
        
        #function = self.functions[str(self.dockwidget.comboBoxFunction.currentText())]
        function = self.functions['dijkstra']
        args = self.getArguments(function.getControlNames(self.version))
        
        empties = []
        for key in args.keys():
            if not args[key]:
                empties.append(key)
        
        if len(empties) > 0:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self.dockwidget, self.dockwidget.windowTitle(),
                'Following argument is not specified.\n' + ','.join(empties))
            return
        
        db = None
        try:
            dbname = str(self.dockwidget.comboBoxDatabase.currentText())            
            db = self.connectionsDB[dbname].connect()
            con = db.con
            
            version = Utils.getPgrVersion(con)
            args['version'] = version
            if (self.version!=version) :
                QMessageBox.warning(self.dockwidget, self.dockwidget.windowTitle(),
                  'versions are different')

            srid, geomType = Utils.getSridAndGeomType(con, args)
            
            function.prepare(self.canvasItemList)       #clears previous route
            query = function.getQuery(args)
            QMessageBox.information(self.dockwidget, self.dockwidget.windowTitle(), 'Geometry Query:' + query)
           
            cur = con.cursor()
            cur.execute(query)
            rows = cur.fetchall()
            if  len(rows) == 0:
                QMessageBox.information(self.dockwidget, self.dockwidget.windowTitle(), 'No paths found in ' + self.getLayerName(args))
            
            args['srid'] = srid
            args['canvas_srid'] = Utils.getCanvasSrid(Utils.getDestinationCrs(self.iface.mapCanvas()))
            Utils.setTransformQuotes(args, srid, args['canvas_srid'])
            #TODO add route as new layer
            function.draw(rows, con, args, geomType, self.canvasItemList, self.iface.mapCanvas())
            
        except psycopg2.DatabaseError, e:
            print "** Database Error"
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self.dockwidget, self.dockwidget.windowTitle(), '%s' % e)
            
        except SystemError, e:
            print "** SystemError Error"
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self.dockwidget, self.dockwidget.windowTitle(), '%s' % e)
            
        finally:
            QApplication.restoreOverrideCursor()
            if db and db.con:
                try:
                    db.con.close()
                except:
                    QMessageBox.critical(self.dockwidget, self.dockwidget.windowTitle(),
                        'server closed the connection unexpectedly')
        
    
    def saveRoute(self):
        """Calculate Route from specified source to target using default postgis dijkstra function.
        
        Saves Route to layer.
        """
        
        print "** saveRoute"
        
        #Clear previous route
        self.removeRoute()
        
        function = self.functions['dijkstra']
        args = self.getArguments(function.getControlNames(self.version))
        
        empties = []
        for key in args.keys():
            if not args[key]:
                empties.append(key)
        
        if len(empties) > 0:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self.dockwidget, self.dockwidget.windowTitle(),
                'Following argument is not specified.\n' + ','.join(empties))
            return
        
        db = None
        try:
            dbname = str(self.dockwidget.comboBoxDatabase.currentText())            
            db = self.connectionsDB[dbname].connect()
            con = db.con
            cur = con.cursor()
            
            version = Utils.getPgrVersion(con)
            args['version'] = version
            if (self.version!=version) :
                QMessageBox.warning(self.dockwidget, self.dockwidget.windowTitle(),
                  'versions are different')

            srid, geomType = Utils.getSridAndGeomType(con, args)
            layerName = self.getLayerName(args)
            args['tmp_table'] = layerName
            
            #Drop table if exists
            if True in [layerName in t for t in db.list_geotables('tmp')]:
                db.delete_table(layerName, 'tmp')
            
            #Save route to new tmp table
            tmpquery = function.getSaveExportQuery(args)
            #QMessageBox.information(self.dockwidget, self.dockwidget.windowTitle(), 'Geometry Query:\n' + tmpquery)
            Utils.logMessage('Export:\n' + tmpquery)
            cur.execute(self.cleanQuery(tmpquery))
            con.commit()
            
            #Query new tmp table
            query = """
                SELECT * FROM tmp.%(tmp_table)s
                """ % args
            query = self.cleanQuery(query)
            #QMessageBox.information(self.dockwidget, self.dockwidget.windowTitle(), 'Geometry Query:\n' + query)
            Utils.logMessage('Export:\n' + query)         
            
            # Save to vector layer
            uri = db.getURI()
            uri.setDataSource("", "(" + query + ")", "path_geom", "", "seq")
            vl = self.iface.addVectorLayer(uri.uri(), layerName, db.getProviderName())
            if not vl:
                QMessageBox.information(self.dockwidget, self.dockwidget.windowTitle(), 'Invalid Layer:\n - No paths found or\n - Failed to create vector layer from query')
            
            # Save layers
            self.projectLayerList['route_psql'] = vl
            self.projectLayerList['tmp_route'] = args['tmp_table']
            
#             # Create VectorLayer > source is SQL Query, so it'll always have to queried again on reload
#             tmpDir = self.getTempDir(layerName)
#             qvl = QgsVectorLayer(uri.uri(), layerName, db.getProviderName())            
#             # Write to tmp shapefile and load to layer for better view performance is qgis
#             QgsVectorFileWriter.writeAsVectorFormat(qvl, tmpDir , "utf-8", None, "ESRI Shapefile")
#             vl = self.iface.addVectorLayer(tmpDir, layerName, "ogr")
#             self.projectLayerList['route_shapefile'] = vl      
            
        except psycopg2.DatabaseError, e:
            print "** Database Error"
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self.dockwidget, self.dockwidget.windowTitle(), '%s' % e)
            
        except SystemError, e:
            print "** SystemError Error"
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self.dockwidget, self.dockwidget.windowTitle(), '%s' % e)
            
        finally:
            QApplication.restoreOverrideCursor()
            if db and db.con:
                try:
                    db.con.close()
                except:
                    QMessageBox.critical(self.dockwidget, self.dockwidget.windowTitle(),
                        'server closed the connection unexpectedly')
                    
    def removeRoute(self):
        """Remove Route from layers and file system.

        """
        
        print "** removeRoute"
        
        # Remove layer from QGIS
        if 'route_psql' in self.projectLayerList:
            layer = self.projectLayerList['route_psql']
            source = layer.dataProvider().dataSourceUri()
            QgsMapLayerRegistry.instance().removeMapLayer(layer)
            del self.projectLayerList['route_psql']
#         else:
#             QMessageBox.information(self.dockwidget, self.dockwidget.windowTitle(), 'There is no route layer to be removed.')

        # Remove Shapefile from disc            
        if 'route_shapefile' in self.projectLayerList:
            del self.projectLayerList['route_shapefile']
                 
            for file in glob.glob(source.split('.')[0]+"*"):
                os.remove(file)
#         else:
#             QMessageBox.information(self.dockwidget, self.dockwidget.windowTitle(), 'There is no route shapefile to be removed.')
                
        # Remove tmp database table
        if 'tmp_route' in self.projectLayerList:
            db = None
            try:
                dbname = str(self.dockwidget.comboBoxDatabase.currentText())            
                db = self.connectionsDB[dbname].connect()
                con = db.con
                    
                #Drop table if exists
                if True in [self.projectLayerList['tmp_route'] in t for t in db.list_geotables('tmp')]:
                    db.delete_table(self.projectLayerList['tmp_route'], 'tmp')            
            except psycopg2.DatabaseError, e:
                print "** Database Error"
                QApplication.restoreOverrideCursor()
                QMessageBox.critical(self.dockwidget, self.dockwidget.windowTitle(), '%s' % e)
            
            finally:
                del self.projectLayerList['tmp_route']
                QApplication.restoreOverrideCursor()
                if db and db.con:
                    try:
                        db.con.close()
                    except:
                        QMessageBox.critical(self.dockwidget, self.dockwidget.windowTitle(),
                            'server closed the connection unexpectedly')
#         else: 
#             QMessageBox.information(self.dockwidget, self.dockwidget.windowTitle(), 'There is no route table to be removed.')
            

    def cleanQuery(self, msgQuery):
        query = msgQuery.replace('\n', ' ')
        query = re.sub(r'\s+', ' ', query)
        query = query.replace('( ', '(')
        query = query.replace(' )', ')')
        query = query.strip()
        return query
    
    def getArguments(self, controls):
        args = {}       #'dict'
        
        if 'comboBoxEdgesSchema' in controls:
            args['edge_schema'] = self.dockwidget.comboBoxEdgesSchema.currentText()
        if 'comboBoxEdgesTable' in controls:
            args['edge_table'] = self.dockwidget.comboBoxEdgesTable.currentText()
        if 'lineEditGeometryColumn' in controls:
            args['geometry'] = self.dockwidget.lineEditGeometryColumn.text()
        if 'lineEditIDColumn' in controls:
            args['id'] = self.dockwidget.lineEditIDColumn.text()

        if 'lineEditSourceColumn' in controls:
            args['source'] = self.dockwidget.lineEditSourceColumn.text()
        
        if 'lineEditTargetColumn' in controls:
            args['target'] = self.dockwidget.lineEditTargetColumn.text()
        
        if 'lineEditCostColumn' in controls:
            args['cost'] = self.dockwidget.lineEditCostColumn.text()
        
        if 'lineEditReverseCostColumn' in controls:
            args['reverse_cost'] = self.dockwidget.lineEditReverseCostColumn.text()
            #args['reverse_cost'] = ', ' + args['reverse_cost'] + '::float8 AS reverse_cost'

        if 'lineEditSelectSourceID' in controls:
            args['source_id'] = self.dockwidget.lineEditSelectSourceID.text()
            args['source_ids'] = self.dockwidget.lineEditSelectSourceID.text()
        
        if 'lineEditSelectTargetID' in controls:
            args['target_id'] = self.dockwidget.lineEditSelectTargetID.text()
            args['target_ids'] = self.dockwidget.lineEditSelectTargetID.text()
        
        if 'checkBoxDirected' in controls:
            args['directed'] = str(self.dockwidget.checkBoxDirected.isChecked()).lower()
        
#         if 'checkBoxUseBBOX' in controls:
#             #args['use_bbox'] = str(self.dockwidget.checkBoxUseBBOX.isChecked()).lower()
#             args['use_bbox'] = 'true'
#         else:
#             args['use_bbox'] = 'false'
        args['use_bbox'] = 'false'
        
        if 'checkBoxHasReverseCost' in controls:
            args['has_reverse_cost'] = str(self.dockwidget.checkBoxHasReverseCost.isChecked()).lower()
            if args['has_reverse_cost'] == 'false':
                args['reverse_cost'] = ' '
            else:
                # ',' prefix needed for the SQL query to be generic for queries with/without reverse_cost
                args['reverse_cost'] = ', ' + args['reverse_cost'] + '::float8 AS reverse_cost'
            
        return args        
    
    
    def setDefaultArguments(self, controls):
        """Loads default arguments and fills the widget boxes with the lables"""
        
        oldReloadMessage = self.reloadMessage
        self.reloadMessage = False
        
        #comboBoxDatabase
        idx = self.dockwidget.comboBoxDatabase.findText('postgres')
        if idx >= 0:
            self.dockwidget.comboBoxDatabase.setCurrentIndex(idx) #reset to previous selection
        else:
            self.dockwidget.comboBoxDatabase.setCurrentIndex(0)
        self.reloadMessage = oldReloadMessage

        #comboBoxEdgesSchema
        idx = self.dockwidget.comboBoxEdgesSchema.findText('nrw_2po')
        if idx >= 0:
            self.dockwidget.comboBoxEdgesSchema.setCurrentIndex(idx) #reset to previous selection
        else:
            self.dockwidget.comboBoxEdgesSchema.setCurrentIndex(0)
            
        #comboBoxEdgesTable
        idx = self.dockwidget.comboBoxEdgesTable.findText('nrw_2po_4pgr')
        if idx >= 0:
            self.dockwidget.comboBoxEdgesTable.setCurrentIndex(idx) #reset to previous selection
        else:
            self.dockwidget.comboBoxEdgesTable.setCurrentIndex(0)
            
        #comboBoxVerticesTable
        idx = self.dockwidget.comboBoxVerticesTable.findText('nrw_2po_4pgr_vertices_pgr')
        if idx >= 0:
            self.dockwidget.comboBoxVerticesTable.setCurrentIndex(idx) #reset to previous selection
        else:
            self.dockwidget.comboBoxVerticesTable.setCurrentIndex(0)

        if 'lineEditGeometryColumn' in controls:
            self.dockwidget.lineEditGeometryColumn.setText('geom')
        if 'lineEditIDColumn' in controls:
            self.dockwidget.lineEditIDColumn.setText('id')
 
        if 'lineEditSourceColumn' in controls:
            self.dockwidget.lineEditSourceColumn.setText('source')
         
        if 'lineEditTargetColumn' in controls:
            self.dockwidget.lineEditTargetColumn.setText('target')
         
        if 'lineEditCostColumn' in controls:
            self.dockwidget.lineEditCostColumn.setText('cost')
         
        if 'lineEditReverseCostColumn' in controls:
            self.dockwidget.lineEditReverseCostColumn.setText('reverse_cost')
 
        if 'lineEditSelectSourceID' in controls:
            self.dockwidget.lineEditSelectSourceID.setText('437021')
            #self.dockwidget.lineEditSelectSourceID.insert(self.getRandomID())
         
        if 'lineEditSelectTargetID' in controls:
            self.dockwidget.lineEditSelectTargetID.setText('366598')
            #self.dockwidget.lineEditSelectTargetID.insert(self.getRandomID())
         
        if 'checkBoxDirected' in controls:
            self.dockwidget.checkBoxDirected.setChecked(True)
            
        if 'checkBoxHasReverseCost' in controls:
            self.dockwidget.checkBoxHasReverseCost.setChecked(True)
            
    
    def getLayerName(self, args, letter=''):
        function = self.functions['dijkstra']

        layerName = function.getName()

        if 'source_id' in args:
            layerName +=  args['source_id']

        layerName += "to"
        if 'target_id' in args:
            layerName += args['target_id']

        return layerName 
    
    def getTempDir(self, layerName):
        
        return "/tmp/" + layerName + ".shp"
        
            
    def clearPreview(self):
        
        print "** clearPreview"
        #self.dock.lineEditIds.setText("")
        for marker in self.idsVertexMarkers:
            marker.setVisible(False)
        self.idsVertexMarkers = []

        #self.dock.lineEditSourceIds.setText("")
        for marker in self.sourceIdsVertexMarkers:
            marker.setVisible(False)
        self.sourceIdsVertexMarkers = []

        #self.dock.lineEditTargetIds.setText("")
        for marker in self.targetIdsVertexMarkers:
            marker.setVisible(False)
        self.targetIdsVertexMarkers = []

        #self.dock.lineEditPcts.setText("")
        #self.dock.lineEditSourceId.setText("")
        self.sourceIdVertexMarker.setVisible(False)
        #self.dock.lineEditSourcePos.setText("0.5")
        #self.dock.lineEditTargetId.setText("")
        self.targetIdVertexMarker.setVisible(False)
        #self.dock.lineEditTargetPos.setText("0.5")
        for rubberBand in self.idsRubberBands:
            rubberBand.reset(Utils.getRubberBandType(False))
        self.idsRubberBands = []
        self.sourceIdRubberBand.reset(Utils.getRubberBandType(False))
        self.targetIdRubberBand.reset(Utils.getRubberBandType(False))
        for marker in self.canvasItemList['markers']:
            marker.setVisible(False)
        self.canvasItemList['markers'] = []
        for anno in self.canvasItemList['annotations']:
            try:
                anno.setVisible(False)
                self.iface.mapCanvas().scene().removeItem(anno)
            except RuntimeError, e:
                QApplication.restoreOverrideCursor()
                QMessageBox.critical(self.dock, self.dock.windowTitle(), '%s' % e)
        self.canvasItemList['annotations'] = []
        for path in self.canvasItemList['paths']:
            path.reset(Utils.getRubberBandType(False))
        self.canvasItemList['paths'] = []
        self.canvasItemList['path'].reset(Utils.getRubberBandType(False))
        self.canvasItemList['area'].reset(Utils.getRubberBandType(True))


    def loadSettings(self):
        
        print "** loadSettings"
        
        settings = QSettings()
        idx = self.dockwidget.comboBoxDatabase.findText(Utils.getStringValue(settings, '/orientationMapsCreator/Database', ''))
        if idx >= 0:
            self.dockwidget.comboBoxDatabase.setCurrentIndex(idx)
        
        idx = self.dockwidget.comboBoxEdgesSchema.findText(Utils.getStringValue(settings, '/orientationMapsCreator/edge_schema', ''))
        if idx >= 0:
            self.dockwidget.comboBoxEdgesSchema.setCurrentIndex(idx)
            
        idx = self.dockwidget.comboBoxEdgesTable.findText(Utils.getStringValue(settings, '/orientationMapsCreator/edges_table', ''))
        if idx >= 0:
            self.dockwidget.comboBoxEdgesTable.setCurrentIndex(idx)

        idx = self.dockwidget.comboBoxVerticesTable.findText(Utils.getStringValue(settings, '/orientationMapsCreator/vertices_table', ''))
        if idx >= 0:
            self.dockwidget.comboBoxVerticesTable.setCurrentIndex(idx)
        
        self.dockwidget.lineEditGeometryColumn.setText(Utils.getStringValue(settings, '/orientationMapsCreator/sql/geometry', 'geom'))
        self.dockwidget.lineEditIDColumn.setText(Utils.getStringValue(settings, '/orientationMapsCreator/sql/id', 'id'))
        self.dockwidget.lineEditSourceColumn.setText(Utils.getStringValue(settings, '/orientationMapsCreator/sql/source', 'source'))
        self.dockwidget.lineEditTargetColumn.setText(Utils.getStringValue(settings, '/orientationMapsCreator/sql/target', 'target'))
        self.dockwidget.lineEditCostColumn.setText(Utils.getStringValue(settings, '/orientationMapsCreator/sql/cost', 'cost'))
        self.dockwidget.lineEditReverseCostColumn.setText(Utils.getStringValue(settings, '/orientationMapsCreator/sql/reverse_cost', 'reverse_cost'))
        
        self.dockwidget.lineEditSelectSourceID.setText(Utils.getStringValue(settings, '/orientationMapsCreator/source_id', '437021'))
        self.dockwidget.lineEditSelectTargetID.setText(Utils.getStringValue(settings, '/orientationMapsCreator/target_id', '366598'))

        self.dockwidget.checkBoxDirected.setChecked(Utils.getBoolValue(settings, '/orientationMapsCreator/directed', False))
        self.dockwidget.checkBoxHasReverseCost.setChecked(Utils.getBoolValue(settings, '/orientationMapsCreator/has_reverse_cost', False))
       
        
    def saveSettings(self):
        
        print "** saveSettings"
        
        settings = QSettings()
        settings.setValue('/orientationMapsCreator/Database', self.dockwidget.comboBoxDatabase.currentText())
        settings.setValue('/orientationMapsCreator/edge_schema', self.dockwidget.comboBoxEdgesSchema.currentText())
        
        settings.setValue('/orientationMapsCreator/edges_table', self.dockwidget.comboBoxEdgesTable.currentText())
        settings.setValue('/orientationMapsCreator/vertices_table', self.dockwidget.comboBoxVerticesTable.currentText())
        settings.setValue('/orientationMapsCreator/sql/geometry', self.dockwidget.lineEditGeometryColumn.text())

        settings.setValue('/orientationMapsCreator/sql/id', self.dockwidget.lineEditIDColumn.text())
        settings.setValue('/orientationMapsCreator/sql/source', self.dockwidget.lineEditSourceColumn.text())
        settings.setValue('/orientationMapsCreator/sql/target', self.dockwidget.lineEditTargetColumn.text())
        settings.setValue('/orientationMapsCreator/sql/cost', self.dockwidget.lineEditCostColumn.text())
        settings.setValue('/orientationMapsCreator/sql/reverse_cost', self.dockwidget.lineEditReverseCostColumn.text())

        settings.setValue('/orientationMapsCreator/source_id', self.dockwidget.lineEditSelectSourceID.text())
        settings.setValue('/orientationMapsCreator/target_id', self.dockwidget.lineEditSelectTargetID.text())

        settings.setValue('/orientationMapsCreator/directed', self.dockwidget.checkBoxDirected.isChecked())
        settings.setValue('/orientationMapsCreator/has_reverse_cost', self.dockwidget.checkBoxHasReverseCost.isChecked())
    #--------------------------------------------------------------------------

    def run(self):
        """Run method that loads and starts the plugin"""
        
        print "** run"   # this is executed when the widget/plugin is opened/activated
        
        if not self.pluginIsActive:
            self.pluginIsActive = True
            
            print "** STARTING orientationMapsCreator"

            # dockwidget may not exist if:
            #    first run of plugin
            #    removed on close (see self.onClosePlugin method)
            if self.dockwidget == None:
                # Create the dockwidget (after translation) and keep reference
                self.dockwidget = orientationMapsCreatorDockWidget()

            # connect to provide cleanup on closing of dockwidget
            self.dockwidget.closingPlugin.connect(self.onClosePlugin)

            # show the dockwidget
            # TODO: fix to allow choice of dock location
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dockwidget)
            self.dockwidget.show()

