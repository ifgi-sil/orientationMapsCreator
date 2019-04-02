# -*- coding: utf-8 -*-

#from PyQt4.QtCore import *
from PyQt4.QtCore import Qt, QSettings, QObject, SIGNAL, QTranslator, QCoreApplication
#from PyQt4.QtGui import *
from PyQt4.QtGui import QIcon, QAction, QApplication, QMessageBox, QMessageBox, QColor
#from qgis.core import *
from qgis.core import QgsLayerTreeLayer, QgsProject, QgsMapLayerRegistry, QgsVectorLayer, QgsFeature, QgsRectangle, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsGeometry
#from qgis.gui import *
from qgis.gui import QgsVertexMarker, QgsRubberBand, QgsMapToolEmitPoint
from orientationMapsCreator_dockwidget import orientationMapsCreatorDockWidget
import orientationMapsCreator_utils as Utils
import dbConnection
import os
from __builtin__ import str
plugin_path = os.path.dirname(os.path.realpath(__file__)) # Potentially fix subdirectories
import psycopg2     #DatabaseError
import re           #RegularExpressions
import glob
import timeit

import sys
sys.path.append('/usr/share/qgis/python/plugins')   #Import python processing tools
from processing.core.Processing import Processing
Processing.initialize()
#from processing.tools import *


# Initialize Qt resources from file resources.py
import resources
#from qgis._core import QgsVectorLayer

conn = dbConnection.ConnectionManager()

from functions import routeCalculator

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
    
    FIND_RADIUS = 10
    

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
        
        # Layer Panel Groups
        self.projectLayerPanel = {}
        
        #Layers added to the project
        self.projectLayerList = {}  
        
        # DB-Schema List for saving previous selections in comboBoxes
        self.dbResultsSchemaSettings = {}
        self.dbSchemaSettings = {}
        self.dbEdgesTableSettings = {}
        self.dbVerticesTableSettings = {}
        self.dbRouteTableSettings = {}
        self.dbOpenNRWSchemaSettings = {}
        self.dbOpenNRWDLMSettings = {}
        self.dbOSMSchemaSettings = {}
        self.dbOSMPointsSettings = {}
        self.dbOSMLinesSettings = {}
        self.dbOSMPolygonsSettings = {}

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
        
        
        ## Test routeCalculator
        self.routeCalculator = routeCalculator.routeCalculator()

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
            
        
        self.idsEmitPoint = QgsMapToolEmitPoint(self.iface.mapCanvas())
        self.sourceIdEmitPoint = QgsMapToolEmitPoint(self.iface.mapCanvas())
        self.targetIdEmitPoint = QgsMapToolEmitPoint(self.iface.mapCanvas())
        
                 
        # connect UI actions to methods
        QObject.connect(self.dockwidget.btnPrepareProject, SIGNAL("clicked()"), self.prepareProject)
        
        QObject.connect(self.dockwidget.btnLoadDefaults, SIGNAL("clicked()"), self.loadDefaultConnections)
        QObject.connect(self.dockwidget.btnRunAllFunctions, SIGNAL("clicked()"), self.runAllFunctions)        
        QObject.connect(self.dockwidget.btnClearDatasets, SIGNAL("clicked()"), self.clearDatasets)
        QObject.connect(self.dockwidget.btnDatabaseRefresh, SIGNAL("clicked()"), self.reloadConnections)
        
        QObject.connect(self.dockwidget.comboBoxDatabase, SIGNAL("currentIndexChanged(const QString&)"), self.updateDatabaseConnectionEnabled)
        QObject.connect(self.dockwidget.comboBoxResultsSchema, SIGNAL("currentIndexChanged(const QString&)"), self.updateResultsSchemaIndexChanged)
        QObject.connect(self.dockwidget.comboBoxEdgesSchema, SIGNAL("currentIndexChanged(const QString&)"), self.updateEdgesSchemaIndexChanged)
        QObject.connect(self.dockwidget.comboBoxEdgesTable, SIGNAL("currentIndexChanged(const QString&)"), self.updateEdgesTableIndexChanged)
        QObject.connect(self.dockwidget.comboBoxVerticesTable, SIGNAL("currentIndexChanged(const QString&)"), self.updateVerticesTableIndexChanged)
        QObject.connect(self.dockwidget.comboBoxRouteTable, SIGNAL("currentIndexChanged(const QString&)"), self.updateRouteTableIndexChanged)
        
        
        
        QObject.connect(self.dockwidget.btnPreviewRoute, SIGNAL("clicked()"), self.previewRoute)
        QObject.connect(self.dockwidget.btnClearPreview, SIGNAL("clicked()"), self.clearPreview)
        QObject.connect(self.dockwidget.btnSaveRoute, SIGNAL("clicked()"), self.saveRoute)
        QObject.connect(self.dockwidget.btnRemoveRoute, SIGNAL("clicked()"), self.removeRoute)
        QObject.connect(self.dockwidget.btnLoadRoute, SIGNAL("clicked()"), self.loadRoute)
        #QObject.connect(self.dockwidget.btnSaveRoute, SIGNAL("clicked()"), self.routeCalculator.saveRoute)
        
        QObject.connect(self.dockwidget.btnBufferNetwork, SIGNAL("clicked()"), self.bufferNetwork)
        QObject.connect(self.dockwidget.btnAnalyzeRoute, SIGNAL("clicked()"), self.analyzeRoute)
        
        # One source id can be selected in some functions/version
        QObject.connect(self.dockwidget.btnSelectSourceID, SIGNAL("clicked(bool)"), self.selectSourceId)
        QObject.connect(self.sourceIdEmitPoint, SIGNAL("canvasClicked(const QgsPoint&, Qt::MouseButton)"), self.setSourceId)
        QObject.connect(self.dockwidget.btnSelectRandomSource, SIGNAL("clicked()"), self.setRandomSourceId)
        QObject.connect(self.dockwidget.btnSelectTargetID, SIGNAL("clicked(bool)"), self.selectTargetId)
        QObject.connect(self.targetIdEmitPoint, SIGNAL("canvasClicked(const QgsPoint&, Qt::MouseButton)"), self.setTargetId)
        QObject.connect(self.dockwidget.btnSelectRandomTarget, SIGNAL("clicked()"), self.setRandomTargetId)
        
        
        # OPEN NRW
        QObject.connect(self.dockwidget.comboBoxOpenNRWSchema, SIGNAL("currentIndexChanged(const QString&)"), self.updateOpenNRWSchemaIndexChanged)
        QObject.connect(self.dockwidget.comboBoxOpenNRWDLM, SIGNAL("currentIndexChanged(const QString&)"), self.updateOpenNRWDLMIndexChanged)
        
        QObject.connect(self.dockwidget.btnGetEnvironmentalRegions, SIGNAL("clicked()"), self.getEnvironmentalRegions)
        QObject.connect(self.dockwidget.btnAddRegionsNetwork, SIGNAL("clicked()"), self.addRegionsNetwork)
        QObject.connect(self.dockwidget.btnGetAdministrativeRegions, SIGNAL("clicked()"), self.getAdministrativeRegions)
        
        
        # OSM
        QObject.connect(self.dockwidget.comboBoxOSMSchema, SIGNAL("currentIndexChanged(const QString&)"), self.updateOSMSchemaIndexChanged)
        QObject.connect(self.dockwidget.comboBoxOSMPointsTable, SIGNAL("currentIndexChanged(const QString&)"), self.updateOSMPointsIndexChanged)
        QObject.connect(self.dockwidget.comboBoxOSMLinesTable, SIGNAL("currentIndexChanged(const QString&)"), self.updateOSMLinesIndexChanged)
        QObject.connect(self.dockwidget.comboBoxOSMPolygonsTable, SIGNAL("currentIndexChanged(const QString&)"), self.updateOSMPolygonsIndexChanged)
        
        
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
        
        
    # --------------------------------------------------------------------------

    
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
        
        #print "** loadDefaultConnections"
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
        
        # temp save previous results_schema
        curResultsSchema = ''
        if dbname in self.dbResultsSchemaSettings:
            curResultsSchema = self.dbResultsSchemaSettings[dbname]

        self.dockwidget.comboBoxResultsSchema.clear()
        
        # temp save previous edges_schema
        curSchema = ''
        if dbname in self.dbSchemaSettings:
            curSchema = self.dbSchemaSettings[dbname]

        self.dockwidget.comboBoxEdgesSchema.clear()
        
        # temp save previous open_nrw_schema
        curOpenNRWSchema = ''
        if dbname in self.dbOpenNRWSchemaSettings:
            curOpenNRWSchema = self.dbOpenNRWSchemaSettings[dbname]

        self.dockwidget.comboBoxOpenNRWSchema.clear()
    
        # retrieve schemas for new database
        try:
            db = self.connectionsDB[dbname].connect()
            con = db.con           
            for schema in db.list_schemas():
                self.dockwidget.comboBoxResultsSchema.addItem(schema[1])
                self.dockwidget.comboBoxEdgesSchema.addItem(schema[1])
                self.dockwidget.comboBoxOpenNRWSchema.addItem(schema[1])
                self.dockwidget.comboBoxOSMSchema.addItem(schema[1])
                #print "** schema = ", schema[1]
                
        except dbConnection.DbError, e:
            Utils.logMessage("dbname:" + dbname + ", " + e.msg)

        finally:
            if db and db.con:
                db.con.close()
                
                
        #restore previously selected results schema if exists
        idx = self.dockwidget.comboBoxResultsSchema.findText(curResultsSchema)
        if idx >= 0:
            self.dockwidget.comboBoxResultsSchema.setCurrentIndex(idx) #reset to previous selection
        else:
            self.dockwidget.comboBoxResultsSchema.setCurrentIndex(0)
            
        self.dbResultsSchemaSettings[dbname] = str(self.dockwidget.comboBoxResultsSchema.currentText())
        
        
        #restore previously selected schema if exists
        idx = self.dockwidget.comboBoxEdgesSchema.findText(curSchema)
        if idx >= 0:
            self.dockwidget.comboBoxEdgesSchema.setCurrentIndex(idx) #reset to previous selection
        else:
            self.dockwidget.comboBoxEdgesSchema.setCurrentIndex(0)
            
        self.dbSchemaSettings[dbname] = str(self.dockwidget.comboBoxEdgesSchema.currentText())
        
        
        #restore previously selected open_nrw_schema if exists
        idx = self.dockwidget.comboBoxOpenNRWSchema.findText(curOpenNRWSchema)
        if idx >= 0:
            self.dockwidget.comboBoxOpenNRWSchema.setCurrentIndex(idx) #reset to previous selection
        else:
            self.dockwidget.comboBoxOpenNRWSchema.setCurrentIndex(0)
            
        self.dbOpenNRWSchemaSettings[dbname] = str(self.dockwidget.comboBoxOpenNRWSchema.currentText())
        

        self.updateEdgesSchemaIndexChanged()
        
        
    def updateResultsSchemaIndexChanged(self):
        """Reload Tables of connected Schema"""

        #print "** updateResultsSchemaIndexChanged"
        
        dbname = str(self.dockwidget.comboBoxDatabase.currentText())
        if dbname =='':
            return
        
        schema = str(self.dockwidget.comboBoxResultsSchema.currentText())
        self.dbResultsSchemaSettings[dbname] = schema
        
        # temp save previous route table
        curRouteTable = ''
        if dbname+'.'+schema in self.dbRouteTableSettings:
            curRouteTable = self.dbRouteTableSettings[dbname+'.'+schema]
            
        # empty route fields
        self.dockwidget.comboBoxRouteTable.clear()
        
        # retrieve route tables for new schema
        try:
            db = self.connectionsDB[dbname].connect()
            con = db.con
            for table in db.list_geotables(schema):
                self.dockwidget.comboBoxRouteTable.addItem(table[0])
                #print "** edgesVerticesTable = ", table[0]
                
        except dbConnection.DbError, e:
            Utils.logMessage("dbname:" + dbname + ", " + e.msg)

        finally:
            if db and db.con:
                db.con.close()
                
        # restore previously selected route table if exists
        idx = self.dockwidget.comboBoxRouteTable.findText(curRouteTable)
        if idx >= 0:
            self.dockwidget.comboBoxRouteTable.setCurrentIndex(idx) #reset to previous selection
            # comboBox updates but route load needs to be triggered manually if required
        else:
            self.dockwidget.comboBoxRouteTable.setCurrentIndex(0)   
        self.dbRouteTableSettings[dbname+'.'+schema] = str(self.dockwidget.comboBoxRouteTable.currentText())
        

    def updateEdgesSchemaIndexChanged(self):
        """Reload Tables of connected Schema"""

        #print "** updateEdgesSchemaIndexChanged"
        
        dbname = str(self.dockwidget.comboBoxDatabase.currentText())
        if dbname =='':
            return
        
        # save name of changed schema
        schema = str(self.dockwidget.comboBoxEdgesSchema.currentText())
        self.dbSchemaSettings[dbname] = schema
        
        # temp save previous edges table
        curEdgesTable = ''
        if dbname+'.'+schema in self.dbEdgesTableSettings:
            curEdgesTable = self.dbEdgesTableSettings[dbname+'.'+schema]
            
        # temp save previous vertices table
        curVerticesTable = ''
        if dbname+'.'+schema in self.dbVerticesTableSettings:
            curVerticesTable = self.dbVerticesTableSettings[dbname+'.'+schema]
        
        # empty edges and vertices fields
        self.dockwidget.comboBoxEdgesTable.clear()
        self.dockwidget.comboBoxVerticesTable.clear()
        
        # retrieve edges and vertices tables for new schema
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
                
        # restore previously selected edges table if exists
        idx = self.dockwidget.comboBoxEdgesTable.findText(curEdgesTable)
        if idx >= 0:
            self.dockwidget.comboBoxEdgesTable.setCurrentIndex(idx) #reset to previous selection
        else:
            self.dockwidget.comboBoxEdgesTable.setCurrentIndex(0)   
        self.dbEdgesTableSettings[dbname+'.'+schema] = str(self.dockwidget.comboBoxEdgesTable.currentText())
        
        # restore previously selected edges table if exists
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
        schema = str(self.dockwidget.comboBoxResultsSchema.currentText())
        table = str(self.dockwidget.comboBoxVerticesTable.currentText())
        self.dbVerticesTableSettings[dbname+'.'+schema] = table
        
    
    def updateRouteTableIndexChanged(self):
            
        #print "** updateRouteTableIndexChanged"
        
        dbname = str(self.dockwidget.comboBoxDatabase.currentText())        
        schema = str(self.dockwidget.comboBoxEdgesSchema.currentText())
        table = str(self.dockwidget.comboBoxRouteTable.currentText())
        self.dbRouteTableSettings[dbname+'.'+schema] = table
        
    
    def updateOpenNRWSchemaIndexChanged(self):
        """Reload Tables of OPEN NRW Schema"""

        #print "** updateOpenNRWSchemaIndexChanged"
        
        dbname = str(self.dockwidget.comboBoxDatabase.currentText())
        if dbname =='':
            return
        
        schema = str(self.dockwidget.comboBoxOpenNRWSchema.currentText())
        self.dbOpenNRWSchemaSettings[dbname] = schema
        
        
        # temp save previous edges table
        curDLM = ''
        if dbname+'.'+schema in self.dbOpenNRWDLMSettings:
            curDLM = self.dbOpenNRWDLMSettings[dbname+'.'+schema]
            
        # empty edges and vertices fields
        self.dockwidget.comboBoxOpenNRWDLM.clear()

        
        # retrieve edges and vertices tables for new schema
        try:
            db = self.connectionsDB[dbname].connect()
            con = db.con
            for table in db.list_geotables(schema):
                self.dockwidget.comboBoxOpenNRWDLM.addItem(table[0])
                #print "** edgesVerticesTable = ", table[0]
                
        except dbConnection.DbError, e:
            Utils.logMessage("dbname:" + dbname + ", " + e.msg)

        finally:
            if db and db.con:
                db.con.close()
                
        # restore previously selected edges table if exists
        idx = self.dockwidget.comboBoxOpenNRWDLM.findText(curDLM)
        if idx >= 0:
            self.dockwidget.comboBoxOpenNRWDLM.setCurrentIndex(idx) #reset to previous selection
        else:
            self.dockwidget.comboBoxOpenNRWDLM.setCurrentIndex(0)   
        self.dbOpenNRWDLMSettings[dbname+'.'+schema] = str(self.dockwidget.comboBoxOpenNRWDLM.currentText())
        
    
    def updateOpenNRWDLMIndexChanged(self):
        """Reload Tables of OPEN NRW Schema"""

        #print "** updateOpenNRWDLMIndexChanged"
        
        dbname = str(self.dockwidget.comboBoxDatabase.currentText())        
        schema = str(self.dockwidget.comboBoxOpenNRWSchema.currentText())
        table = str(self.dockwidget.comboBoxOpenNRWDLM.currentText())
        self.dbOpenNRWDLMSettings[dbname+'.'+schema] = table
        
        
    def updateOSMSchemaIndexChanged(self):
        """Reload Tables of OSM Schema"""

        #print "** updateOSMSchemaIndexChanged"
        
        dbname = str(self.dockwidget.comboBoxDatabase.currentText())
        if dbname =='':
            return
        
        schema = str(self.dockwidget.comboBoxOSMSchema.currentText())
        self.dbOSMSchemaSettings[dbname] = schema
        
        
        # temp save previous edges table
        curPoints = ''
        if dbname+'.'+schema in self.dbOSMPointsSettings:
            curPoints = self.dbOSMPointsSettings[dbname+'.'+schema]
            
        
        # temp save previous edges table
        curLines = ''
        if dbname+'.'+schema in self.dbOSMLinesSettings:
            curLines = self.dbOSMLinesSettings[dbname+'.'+schema]
            
        curPolygons = ''
        if dbname+'.'+schema in self.dbOSMPolygonsSettings:
            curPolygons = self.dbOSMPolygonsSettings[dbname+'.'+schema]
            
        # empty edges and vertices fields
        self.dockwidget.comboBoxOSMPointsTable.clear()
        self.dockwidget.comboBoxOSMLinesTable.clear()
        self.dockwidget.comboBoxOSMPolygonsTable.clear()

        
        # retrieve edges and vertices tables for new schema
        try:
            db = self.connectionsDB[dbname].connect()
            con = db.con
            for table in db.list_geotables(schema):
                self.dockwidget.comboBoxOSMPointsTable.addItem(table[0])
                self.dockwidget.comboBoxOSMLinesTable.addItem(table[0])
                self.dockwidget.comboBoxOSMPolygonsTable.addItem(table[0])
                
        except dbConnection.DbError, e:
            Utils.logMessage("dbname:" + dbname + ", " + e.msg)

        finally:
            if db and db.con:
                db.con.close()
                
        # restore previously selected edges table if exists
        idx = self.dockwidget.comboBoxOSMPointsTable.findText(curPoints)
        if idx >= 0:
            self.dockwidget.comboBoxOSMPointsTable.setCurrentIndex(idx) #reset to previous selection
        else:
            self.dockwidget.comboBoxOSMPointsTable.setCurrentIndex(0)   
        self.dbOSMPointsSettings[dbname+'.'+schema] = str(self.dockwidget.comboBoxOSMPointsTable.currentText())
        
        idx = self.dockwidget.comboBoxOSMLinesTable.findText(curLines)
        if idx >= 0:
            self.dockwidget.comboBoxOSMLinesTable.setCurrentIndex(idx) #reset to previous selection
        else:
            self.dockwidget.comboBoxOSMLinesTable.setCurrentIndex(0)   
        self.dbOSMLinesSettings[dbname+'.'+schema] = str(self.dockwidget.comboBoxOSMLinesTable.currentText())
        
        idx = self.dockwidget.comboBoxOSMPolygonsTable.findText(curPolygons)
        if idx >= 0:
            self.dockwidget.comboBoxOSMPolygonsTable.setCurrentIndex(idx) #reset to previous selection
        else:
            self.dockwidget.comboBoxOSMPolygonsTable.setCurrentIndex(0)   
        self.dbOSMPolygonsSettings[dbname+'.'+schema] = str(self.dockwidget.comboBoxOSMPolygonsTable.currentText())
        
    def updateOSMPointsIndexChanged(self):
        """Reload Tables of OSM Schema"""

        #print "** updateOSMPointsIndexChanged"
        
        dbname = str(self.dockwidget.comboBoxDatabase.currentText())        
        schema = str(self.dockwidget.comboBoxOSMSchema.currentText())
        table = str(self.dockwidget.comboBoxOSMPointsTable.currentText())
        self.dbOSMPointsSettings[dbname+'.'+schema] = table
        
    def updateOSMLinesIndexChanged(self):
        """Reload Tables of OSM Schema"""

        #print "** updateOSMLinesIndexChanged"
        
        dbname = str(self.dockwidget.comboBoxDatabase.currentText())        
        schema = str(self.dockwidget.comboBoxOSMSchema.currentText())
        table = str(self.dockwidget.comboBoxOSMLinesTable.currentText())
        self.dbOSMLinesSettings[dbname+'.'+schema] = table
        
    def updateOSMPolygonsIndexChanged(self):
        """Reload Tables of OSM Schema"""

        #print "** updateOSMPolygonsIndexChanged"
        
        dbname = str(self.dockwidget.comboBoxDatabase.currentText())        
        schema = str(self.dockwidget.comboBoxOSMSchema.currentText())
        table = str(self.dockwidget.comboBoxOSMPolygonsTable.currentText())
        self.dbOSMPolygonsSettings[dbname+'.'+schema] = table
        
    # --------------------------------------------------------------------------
    # Plugin Functions
    
    def prepareProject(self):
        """Modify layer panel to add subsequent layers directly into right groups
        
        """
        
        print "** prepareProject"
        
        root = QgsProject.instance().layerTreeRoot()
        self.projectLayerPanel['root'] = root
        
        self.projectLayerPanel['default'] = root.addGroup("Default")
        self.projectLayerPanel['route'] = root.addGroup("Route")
        self.projectLayerPanel['network_selection'] = root.addGroup("Network Selection")
        self.projectLayerPanel['point_features'] = root.addGroup("Point Features")
        self.projectLayerPanel['line_features'] = root.addGroup("Line Features")
        self.projectLayerPanel['polygon_features'] = root.addGroup("Polygon Features")
        self.projectLayerPanel['structural_regions'] = root.addGroup("Structural Regions")
        self.projectLayerPanel['administrative_regions'] = self.projectLayerPanel['structural_regions'].addGroup("Administrative Regions")
        self.projectLayerPanel['environmental_regions'] = self.projectLayerPanel['structural_regions'].addGroup("Environmental Regions")

    
    def runAllFunctions(self):
        """Run all functions one after another.

        """

        print "** runAllFunctions"
        
        start = timeit.default_timer()
        
        self.dockwidget.btnSaveRoute.click()
        self.dockwidget.btnBufferNetwork.click()
        self.dockwidget.btnAnalyzeRoute.click() 
        self.dockwidget.btnGetEnvironmentalRegions.click() 
        self.dockwidget.btnAddRegionsNetwork.click() 
        
        stop = timeit.default_timer()
        
        print('runAllFunctions time: ', stop - start)  
        
    def clearDatasets(self):
        """Clear all datasets from previous calculations.

        """

        print "** clearDatasets"
        
        for l in self.projectLayerList.copy():
            layer = self.projectLayerList[l]
            #source = layer.dataProvider().dataSourceUri()
            QgsMapLayerRegistry.instance().removeMapLayer(layer)
            del layer
            
        for p in self.projectLayerPanel.copy():
            panel = self.projectLayerPanel[p]
            if panel != self.projectLayerPanel['root']:
                self.projectLayerPanel['root'].removeChildNode(panel)
                del panel
            
        del self.projectLayerPanel['root']
        
    
    
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
            #QMessageBox.information(self.dockwidget, self.dockwidget.windowTitle(), 'Geometry Query:' + query)
           
            cur = con.cursor()
            cur.execute(query)
            rows = cur.fetchall()
            if  len(rows) == 0:
                QMessageBox.information(self.dockwidget, self.dockwidget.windowTitle(), 'No paths found in ' + self.getLayerName(args))
                return
            
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
        start = timeit.default_timer()
        
        #Prepare project if not yet done
        if not 'root' in self.projectLayerPanel.keys():
            self.prepareProject()
        
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
            args['tmp_route_table'] = layerName
            
            #Drop table if exists
            if True in [layerName in t for t in db.list_geotables(args['results_schema'])]:
                db.delete_table(layerName, args['results_schema'])
            
            #Save route to new tmp table
            query = function.getSaveExportQuery(args)
            #QMessageBox.information(self.dockwidget, self.dockwidget.windowTitle(), 'Geometry Query:\n' + query)
            Utils.logMessage('Export:\n' + query)
            cur.execute(self.cleanQuery(query))
            con.commit()
            
            # Create Index
            db.create_spatial_index(args['tmp_route_table'], args['results_schema'], 'path_geom')
            
            # Specify tmp table in uri for loading in qgis as vector layer
            uri = db.getURI()     
            uri.setDataSource(args['results_schema'], layerName, "path_geom", "", "seq")     #path_geom holds route segments in correct subsequent order != geom
            
            # Save to vector layer
            vl = self.iface.addVectorLayer(uri.uri(), layerName, db.getProviderName())  
            if not vl:
                QMessageBox.information(self.dockwidget, self.dockwidget.windowTitle(), 'Invalid Layer:\n - No paths found or\n - Failed to create vector layer from query')
                return
            # Style layer
            vl.loadNamedStyle(plugin_path + '/assets/styles/route.qml')
            
            
            # Save layers
            self.projectLayerList['route_psql'] = vl
            self.projectLayerList['tmp_route_table'] = args['tmp_route_table']
            
            # set comboBoxRouteTable to this route
            idx = self.dockwidget.comboBoxRouteTable.findText(args['tmp_route_table'])
            if idx >= 0:
                self.dockwidget.comboBoxRouteTable.setCurrentIndex(idx)
            
            
            # Move layer to group
            #self.projectLayerPanel['route'].addLayer(vl)
            #self.projectLayerPanel['root'].removeLayer(vl)            
            
            
#             ### save as Shapefile
#             # Create VectorLayer > source is SQL Query, so it'll always have to queried again on reload
#             tmpDir = self.getTempDir(layerName)
#             # Create VectorLayer with the route query as source
#             qvl = QgsVectorLayer(uri.uri(), layerName, db.getProviderName())            
#             # Write the result to tmp shapefile and load to layer for better view performance is qgis
#             QgsVectorFileWriter.writeAsVectorFormat(qvl, tmpDir , "utf-8", None, "ESRI Shapefile")
#             vl = self.iface.addVectorLayer(tmpDir, layerName, "ogr")
#             self.projectLayerList['route_shapefile'] = vl

#             ### use QGIS processing plugin to save as shapefile
#             general.runalg("qgis:exportaddgeometrycolumns", vl, 0, "/tmp/tmp.shp")


#             ### Load route into memory layer
#             feats = [feat for feat in vl.getFeatures()]
#             mem_vl = QgsVectorLayer('LineString?crs=epsg:4326', 'tmp_memory_route', 'memory')
#             #mem_vl.setCrs(vl.crs())
#             mem_pr = mem_vl.dataProvider()
#             mem_pr.addAttributes(vl.dataProvider().fields().toList())
#             mem_vl.updateFields()
#             
#             mem_pr.addFeatures(feats)
#             
#             # Add memory layer as qgis layer
#             QgsMapLayerRegistry.instance().addMapLayer(mem_vl)
#             self.projectLayerList['tmp_memory_route'] = mem_vl
            
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
        
        stop = timeit.default_timer()
        print('saveRoute time: ', stop - start)
        
        #Enable Analyze Route and Buffer Network Buttons
        self.dockwidget.btnBufferNetwork.setEnabled(True)
        self.dockwidget.btnAnalyzeRoute.setEnabled(True)
        
        self.saveRoutePoints(args)
    
    
    def saveRoutePoints(self, args):
        """Retrieve route points for calculated route.
        
        """
        
        print "** saveRoutePoints"
        
        start = timeit.default_timer()
        
        #Check if route layer exists in projectLayerList
        if not 'tmp_route_table' in self.projectLayerList:
            QMessageBox.information(self.dockwidget, self.dockwidget.windowTitle(), 'Route layer does not exist.')
            return
        
        try:
            dbname = str(self.dockwidget.comboBoxDatabase.currentText())            
            db = self.connectionsDB[dbname].connect()
            con = db.con
            cur = con.cursor()
                    
            #Check if route layer exists in DB
            if not True in [self.projectLayerList['tmp_route_table'] in t for t in db.list_geotables(args['results_schema'])]:
                QMessageBox.information(self.dockwidget, self.dockwidget.windowTitle(), 'Route table does not exist.')
                return
            
            args['tmp_vertice_table'] = args['tmp_route_table'] + '_vertices'
            args['tmp_vertice_table_start'] = args['tmp_route_table'] + '_start'
            args['tmp_vertice_table_end'] = args['tmp_route_table'] + '_end'
            
            #Drop table if exists
            if True in [args['tmp_vertice_table'] in t for t in db.list_geotables(args['results_schema'])]:
                db.delete_table(args['tmp_vertice_table'], args['results_schema'])
            
            
            #Save route points to separate table
            query = """CREATE TABLE %(results_schema)s.%(tmp_vertice_table)s AS
                (SELECT route.seq-1 as seq, vertices.*
                FROM %(results_schema)s.%(tmp_route_table)s as route, %(edge_schema)s.%(vertice_table)s as vertices
                WHERE route._node = vertices.id
                UNION
                SELECT route.seq as seq, vertices.* 
                FROM (SELECT * FROM %(results_schema)s.%(tmp_route_table)s ORDER BY seq DESC LIMIT 1) as route, %(edge_schema)s.%(vertice_table)s as vertices 
                WHERE route._end_vid = vertices.id)""" % args
            #QMessageBox.information(self.dockwidget, self.dockwidget.windowTitle(), 'Geometry Query:\n' + query)
            
            Utils.logMessage('SaveRoutePoints:\n' + query)
            cur.execute(self.cleanQuery(query))
            con.commit()
            
            # Create Index
            db.create_spatial_index(args['tmp_vertice_table'], args['results_schema'], 'geom')
                        
            
            # Specify tmp table in uri
            uri = db.getURI()     
            uri.setDataSource(args['results_schema'], args['tmp_vertice_table'], "geom", "", "seq")     #path_geom holds route segments in correct subsequent order != geom
            
            
            #Save to vector layer
            vl = self.iface.addVectorLayer(uri.uri(), args['tmp_vertice_table'], db.getProviderName())  
            if not vl:
                QMessageBox.information(self.dockwidget, self.dockwidget.windowTitle(), 'Invalid Layer:\n - No paths found or\n - Failed to create vector layer from query')
            self.projectLayerList['vertice_psql'] = vl
            self.projectLayerList['tmp_vertice_table'] = args['tmp_vertice_table']          
            
            
            # Save start pnt
            uri_start = db.getURI()     
            uri_start.setDataSource(args['results_schema'], args['tmp_vertice_table'], "geom", "seq = (SELECT min(seq) FROM "+ args['results_schema'] + "." + args['tmp_vertice_table'] +")", "seq")     #path_geom holds route segments in correct subsequent order != geom
            vl_start = self.iface.addVectorLayer(uri_start.uri(), args['tmp_vertice_table_start'], db.getProviderName())  
            if not vl_start:
                QMessageBox.information(self.dockwidget, self.dockwidget.windowTitle(), 'Invalid Layer:\n - No paths found or\n - Failed to create vector layer from query')
            vl_start.loadNamedStyle(plugin_path + '/assets/styles/route_start_marker.qml')
            self.projectLayerList['vertice_start_psql'] = vl_start
            self.projectLayerList['tmp_vertice_table_start'] = args['tmp_vertice_table_start']
            
            
            # Save end pnt
            uri_end = db.getURI()     
            uri_end.setDataSource(args['results_schema'], args['tmp_vertice_table'], "geom", "seq = (SELECT max(seq) FROM "+ args['results_schema'] + "." + args['tmp_vertice_table'] +")", "seq")     #path_geom holds route segments in correct subsequent order != geom
            vl_end = self.iface.addVectorLayer(uri_end.uri(), args['tmp_vertice_table_end'], db.getProviderName())  
            if not vl_end:
                QMessageBox.information(self.dockwidget, self.dockwidget.windowTitle(), 'Invalid Layer:\n - No paths found or\n - Failed to create vector layer from query')
            vl_end.loadNamedStyle(plugin_path + '/assets/styles/route_end_marker.qml')
            self.projectLayerList['vertice_end_psql'] = vl_end
            self.projectLayerList['tmp_vertice_table_end'] = args['tmp_vertice_table_end']
            
            self.moveRouteLayers()            
            
#             ### Load vertices into memory layer
#             feats = [feat for feat in vl.getFeatures()]
#             mem_vl = QgsVectorLayer('Point?crs=epsg:4326', 'tmp_memory_vertices', 'memory')
#             #mem_vl.setCrs(vl.crs())
#             mem_pr = mem_vl.dataProvider()
#             mem_pr.addAttributes(vl.dataProvider().fields().toList())
#             mem_vl.updateFields()
#             
#             mem_pr.addFeatures(feats)
#             
#             # Add memory layer as qgis layer
#             QgsMapLayerRegistry.instance().addMapLayer(mem_vl)
#             self.projectLayerList['tmp_memory_vertices'] = mem_vl
            
            
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
        
        stop = timeit.default_timer()
        print('saveRoutePoints time: ', stop - start)
        
    
    def loadRoute(self):
        """ Loads Route from database.
        
        """
        
        print "** loadRoute"
        start = timeit.default_timer()
        
        #Prepare project if not yet done
        if not 'root' in self.projectLayerPanel.keys():
            self.prepareProject()
            
        #Clear previous route
        #self.removeRoute()
        #TODO check is already visualized; do nothing if so; remove previous and add if not
        
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
            layerName = self.dockwidget.comboBoxRouteTable.currentText()
            args['tmp_route_table'] = layerName
            
            # Specify tmp table in uri for loading in qgis as vector layer
            uri = db.getURI()     
            uri.setDataSource(args['results_schema'], layerName, "path_geom", "", "seq")     #path_geom holds route segments in correct subsequent order != geom
            
            # Save to vector layer
            vl = self.iface.addVectorLayer(uri.uri(), layerName, db.getProviderName())  
            if not vl:
                QMessageBox.information(self.dockwidget, self.dockwidget.windowTitle(), 'Invalid Layer:\n - No paths found or\n - Failed to create vector layer from query')
                return
            # Style layer
            vl.loadNamedStyle(plugin_path + '/assets/styles/route.qml')
            
            
            # Save layers
            self.projectLayerList['route_psql'] = vl
            self.projectLayerList['tmp_route_table'] = args['tmp_route_table']
            
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
        
        stop = timeit.default_timer()
        print('loadRoute time: ', stop - start)
        
        #Enable Analyze Route and Buffer Network Buttons
        self.dockwidget.btnBufferNetwork.setEnabled(True)
        self.dockwidget.btnAnalyzeRoute.setEnabled(True)
        
        self.loadRoutePoints(args)
        
        
    def loadRoutePoints(self, args):
        """Load route points for existing route.
        
        """
        
        print "** loadRoutePoints"
        
        start = timeit.default_timer()
        
        #Check if route layer exists in projectLayerList
        if not 'tmp_route_table' in self.projectLayerList:
            QMessageBox.information(self.dockwidget, self.dockwidget.windowTitle(), 'Route layer does not exist.')
            return
        
        try:
            dbname = str(self.dockwidget.comboBoxDatabase.currentText())            
            db = self.connectionsDB[dbname].connect()
            con = db.con
            cur = con.cursor()
                    
            #Check if route layer exists in DB
            if not True in [self.projectLayerList['tmp_route_table'] in t for t in db.list_geotables(args['results_schema'])]:
                QMessageBox.information(self.dockwidget, self.dockwidget.windowTitle(), 'Route table does not exist.')
                return
            
            args['tmp_vertice_table'] = args['tmp_route_table'] + '_vertices'
            args['tmp_vertice_table_start'] = args['tmp_route_table'] + '_start'
            args['tmp_vertice_table_end'] = args['tmp_route_table'] + '_end'
            
            
            # Specify tmp table in uri
            uri = db.getURI()     
            uri.setDataSource(args['results_schema'], args['tmp_vertice_table'], "geom", "", "seq")     #path_geom holds route segments in correct subsequent order != geom
            
            
            #Save to vector layer
            vl = self.iface.addVectorLayer(uri.uri(), args['tmp_vertice_table'], db.getProviderName())  
            if not vl:
                QMessageBox.information(self.dockwidget, self.dockwidget.windowTitle(), 'Invalid Layer:\n - No paths found or\n - Failed to create vector layer from query')
            self.projectLayerList['vertice_psql'] = vl
            self.projectLayerList['tmp_vertice_table'] = args['tmp_vertice_table']          
            
            
            # Save start pnt
            uri_start = db.getURI()     
            uri_start.setDataSource(args['results_schema'], args['tmp_vertice_table'], "geom", "seq = (SELECT min(seq) FROM "+ args['results_schema'] + "." + args['tmp_vertice_table'] +")", "seq")     #path_geom holds route segments in correct subsequent order != geom
            vl_start = self.iface.addVectorLayer(uri_start.uri(), args['tmp_vertice_table_start'], db.getProviderName())  
            if not vl_start:
                QMessageBox.information(self.dockwidget, self.dockwidget.windowTitle(), 'Invalid Layer:\n - No paths found or\n - Failed to create vector layer from query')
            vl_start.loadNamedStyle(plugin_path + '/assets/styles/route_start_marker.qml')
            self.projectLayerList['vertice_start_psql'] = vl_start
            self.projectLayerList['tmp_vertice_table_start'] = args['tmp_vertice_table_start']
            
            
            # Save end pnt
            uri_end = db.getURI()     
            uri_end.setDataSource(args['results_schema'], args['tmp_vertice_table'], "geom", "seq = (SELECT max(seq) FROM "+ args['results_schema'] + "." + args['tmp_vertice_table'] +")", "seq")     #path_geom holds route segments in correct subsequent order != geom
            vl_end = self.iface.addVectorLayer(uri_end.uri(), args['tmp_vertice_table_end'], db.getProviderName())  
            if not vl_end:
                QMessageBox.information(self.dockwidget, self.dockwidget.windowTitle(), 'Invalid Layer:\n - No paths found or\n - Failed to create vector layer from query')
            vl_end.loadNamedStyle(plugin_path + '/assets/styles/route_end_marker.qml')
            self.projectLayerList['vertice_end_psql'] = vl_end
            self.projectLayerList['tmp_vertice_table_end'] = args['tmp_vertice_table_end']
            
            self.moveRouteLayers()            
            
            
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
        
        stop = timeit.default_timer()
        print('loadRoutePoints time: ', stop - start)
        
        
    
    def removeRoute(self):
        """Remove Route from layers and file system.

        """
        
        print "** removeRoute"
        
        function = self.functions['dijkstra']
        args = self.getArguments(function.getControlNames(self.version))
        
        # Remove layer from QGIS
        if 'route_psql' in self.projectLayerList:
            layer = self.projectLayerList['route_psql']
            #source = layer.dataProvider().dataSourceUri()
            QgsMapLayerRegistry.instance().removeMapLayer(layer)
            del self.projectLayerList['route_psql']
        #         else:
#             QMessageBox.information(self.dockwidget, self.dockwidget.windowTitle(), 'There is no route layer to be removed.')     
        
        # Remove tmp database table
        if 'tmp_route_table' in self.projectLayerList:
            db = None
            try:
                dbname = str(self.dockwidget.comboBoxDatabase.currentText())            
                db = self.connectionsDB[dbname].connect()
                con = db.con
                    
                #Drop table if exists
                if True in [self.projectLayerList['tmp_route_table'] in t for t in db.list_geotables(args['results_schema'])]:
                    db.delete_table(self.projectLayerList['tmp_route_table'], args['results_schema'])            
            except psycopg2.DatabaseError, e:
                print "** Database Error"
                QApplication.restoreOverrideCursor()
                QMessageBox.critical(self.dockwidget, self.dockwidget.windowTitle(), '%s' % e)
            
            finally:
                del self.projectLayerList['tmp_route_table']
                QApplication.restoreOverrideCursor()
                if db and db.con:
                    try:
                        db.con.close()
                    except:
                        QMessageBox.critical(self.dockwidget, self.dockwidget.windowTitle(),
                            'server closed the connection unexpectedly')
#         else: 
#             QMessageBox.information(self.dockwidget, self.dockwidget.windowTitle(), 'There is no route table to be removed.')
        
#         # Remove memory layer from QGIS
#         if 'tmp_memory_route' in self.projectLayerList:
#             layer = self.projectLayerList['tmp_memory_route']
#             #source = layer.dataProvider().dataSourceUri()
#             QgsMapLayerRegistry.instance().removeMapLayer(layer)
#             del self.projectLayerList['tmp_memory_route']
            
            
        self.removeRoutePoints(args)
        
#         # Remove Shapefile from disc            
#         if 'route_shapefile' in self.projectLayerList:
#             del self.projectLayerList['route_shapefile']
#                  
#             for file in glob.glob(source.split('.')[0]+"*"):
#                 os.remove(file)
#         else:
#             QMessageBox.information(self.dockwidget, self.dockwidget.windowTitle(), 'There is no route shapefile to be removed.')
            
    
    def removeRoutePoints(self, args):
        """Remove Route Points from layers and file system.

        """
        
        print "** removeRoutePoints"
        
        # Remove layer from QGIS
        if 'vertice_psql' in self.projectLayerList:
            layer = self.projectLayerList['vertice_psql']
            #source = layer.dataProvider().dataSourceUri()
            QgsMapLayerRegistry.instance().removeMapLayer(layer)
            del self.projectLayerList['vertice_psql']
        if 'vertice_start_psql' in self.projectLayerList:
            layer = self.projectLayerList['vertice_start_psql']
            #source = layer.dataProvider().dataSourceUri()
            QgsMapLayerRegistry.instance().removeMapLayer(layer)
            del self.projectLayerList['vertice_start_psql']
        if 'vertice_end_psql' in self.projectLayerList:
            layer = self.projectLayerList['vertice_end_psql']
            #source = layer.dataProvider().dataSourceUri()
            QgsMapLayerRegistry.instance().removeMapLayer(layer)
            del self.projectLayerList['vertice_end_psql']
#         else:
#             QMessageBox.information(self.dockwidget, self.dockwidget.windowTitle(), 'There is no route layer to be removed.')
                
        # Remove tmp database table
        if 'tmp_vertice_table' in self.projectLayerList:
            db = None
            try:
                dbname = str(self.dockwidget.comboBoxDatabase.currentText())            
                db = self.connectionsDB[dbname].connect()
                con = db.con
                     
                #Drop table if exists
                if True in [self.projectLayerList['tmp_vertice_table'] in t for t in db.list_geotables(args['results_schema'])]:
                    db.delete_table(self.projectLayerList['tmp_vertice_table'], args['results_schema'])            
            except psycopg2.DatabaseError, e:
                print "** Database Error"
                QApplication.restoreOverrideCursor()
                QMessageBox.critical(self.dockwidget, self.dockwidget.windowTitle(), '%s' % e)
             
            finally:
                del self.projectLayerList['tmp_vertice_table']
                QApplication.restoreOverrideCursor()
                if db and db.con:
                    try:
                        db.con.close()
                    except:
                        QMessageBox.critical(self.dockwidget, self.dockwidget.windowTitle(),
                            'server closed the connection unexpectedly')
#         else: 
#             QMessageBox.information(self.dockwidget, self.dockwidget.windowTitle(), 'There is no vertices table to be removed.')
        
#         # Remove memory layer from QGIS
#         if 'tmp_memory_vertices' in self.projectLayerList:
#             layer = self.projectLayerList['tmp_memory_vertices']
#             #source = layer.dataProvider().dataSourceUri()
#             QgsMapLayerRegistry.instance().removeMapLayer(layer)
#             del self.projectLayerList['tmp_memory_vertices']
            
    
    def bufferNetwork(self):
        """Buffer Network.
        
        """
        
        print "** bufferNetwork"
        
        start = timeit.default_timer()
        
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
            
            args['tmp_route_table'] = self.projectLayerList['tmp_route_table']
            args['edge_table_buffered'] = args['edge_table'] + "_buffered"         
            
            #Buffer network with length of route
            query = """DROP TABLE IF EXISTS %(results_schema)s.%(edge_table_buffered)s;
                SELECT * 
                INTO %(results_schema)s.%(edge_table_buffered)s
                FROM my_route_length_buffer('%(edge_schema)s.%(edge_table)s', '%(results_schema)s.%(tmp_route_table)s', 1)""" % args
            
            print "bufferNetwork query: " + query
            
            Utils.logMessage('Calculate Angles of Route Points:\n' + query)
            cur.execute(self.cleanQuery(query))
            con.commit()
            
            # Create Index
            db.create_spatial_index(args['edge_table_buffered'], args['results_schema'], 'geom')
            
            # Specify tmp table in uri for loading in qgis as vector layer
            uri = db.getURI()     
            uri.setDataSource(args['results_schema'], args['edge_table_buffered'], "geom", "", "seq")     #path_geom holds route segments in correct subsequent order != geom
            
            # Save to vector layer
            vl = self.iface.addVectorLayer(uri.uri(), args['edge_table_buffered'], db.getProviderName())  
            if not vl:
                QMessageBox.information(self.dockwidget, self.dockwidget.windowTitle(), 'Invalid Layer:\n - No paths found or\n - Failed to create vector layer from query')
            # Style layer
            vl.loadNamedStyle(plugin_path + '/assets/styles/osm2po_network_2.qml')
            
            self.projectLayerList['buffered_network_psql'] = vl
            self.projectLayerList['edge_table_buffered'] = args['edge_table_buffered']
            
            self.moveBufferLayer()
            
        except psycopg2.DatabaseError, e:
            print "** Database Error"
            if str(e).__contains__("my_route_length_buffer"):
                print "function does not exist error"
                #create function
                self.createMissingFkt("my_route_length_buffer")
                
                #run bufferNetwork() again
                self.dockwidget.btnBufferNetwork.click()
            else:  
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
        
        stop = timeit.default_timer()
        print('bufferNetwork time: ', stop - start)
        
    
    def analyzeRoute(self):
        """Analyze Route.
        
        ToDos:
            1.) Load decision points into temporary layer / work with temp vertices layer
            2.) Iterate through Vertices from Start to end.
                2.1.) Retrieve incoming and outgoing route segment from route layer.
                2.2.) Retrieve all other connected street segments from network table.
                2.3.) Check if Vertice is a DP --> checkDP()
                    yes --> maybe special treatment for following vertices needed (when eg. roundabout or exit)
                2.4.) Save to DP layer with ID, if DP
            3.) Extend vertices layer with colum that specifies the DP

        """
        
        print "** analyzeRoute"
        
        start = timeit.default_timer()
                
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

            args['tmp_route_table'] = self.projectLayerList['tmp_route_table']
            args['tmp_vertice_table'] = self.projectLayerList['tmp_vertice_table']
            args['tmp_vertice_table_junctions'] = args['tmp_route_table'] + '_junctions'
            args['tmp_vertice_table_dps'] = args['tmp_route_table'] + '_dps'
            args['tmp_vertice_table_any'] = args['tmp_route_table'] + '_any'
            args['edge_table_buffered'] = self.projectLayerList['edge_table_buffered']

            
            #Calculate angles of route vertices
            query_calculate_angles = """ALTER TABLE %(results_schema)s.%(tmp_vertice_table)s
                ADD COLUMN angle numeric;
                UPDATE %(results_schema)s.%(tmp_vertice_table)s a SET angle=new_angle
                FROM (
                    SELECT *,
                        abs(round(degrees(
                        ST_Azimuth(ST_Transform(geom,32632),(lag(ST_Transform(geom,32632),-1) OVER(ORDER BY seq) ))
                        )::decimal,2)) AS new_angle
                    FROM %(results_schema)s.%(tmp_vertice_table)s
                ) b
                WHERE a.id = b.id""" % args
            
            print "analyzeRoute query_calculate_angles: " + query_calculate_angles
            
            Utils.logMessage('Calculate Angles of Route Points:\n' + query_calculate_angles)
            cur.execute(self.cleanQuery(query_calculate_angles))
            con.commit()
            
            
            #Calculate angles of route vertices
            query_analyze_dps = """ALTER TABLE %(results_schema)s.%(tmp_vertice_table)s ADD COLUMN angle_lin_lout numeric;
                ALTER TABLE %(results_schema)s.%(tmp_vertice_table)s ADD COLUMN dp_type integer;
                UPDATE %(results_schema)s.%(tmp_vertice_table)s a SET angle_lin_lout=b.angle, dp_type=b.dp_type
                FROM (
                    SELECT * FROM my_route_get_dp('%(results_schema)s.%(edge_table_buffered)s', '%(results_schema)s.%(tmp_route_table)s', '%(results_schema)s.%(tmp_vertice_table)s', 30)
                ) b
                WHERE a.id = b.id""" % args
                
            print "analyzeRoute query_analyze_dps: " + query_analyze_dps
            
            Utils.logMessage('Analyze DPs of Route Points:\n' + query_analyze_dps)
            cur.execute(self.cleanQuery(query_analyze_dps))
            con.commit()
            
            
            # Specify tmp table in uri
            uri = db.getURI()     
            uri.setDataSource(args['results_schema'], args['tmp_vertice_table'], "geom", "", "seq")     #path_geom holds route segments in correct subsequent order != geom
            
            
            # Save layer as junctions
            vl_junctions = self.iface.addVectorLayer(uri.uri(), args['tmp_vertice_table_junctions'], db.getProviderName())  
            if not vl_junctions:
                QMessageBox.information(self.dockwidget, self.dockwidget.windowTitle(), 'Invalid Layer:\n - No paths found or\n - Failed to create vector layer from query')
            vl_junctions.loadNamedStyle(plugin_path + '/assets/styles/route_junctions.qml')
            self.projectLayerList['vertice_junctions_psql'] = vl_junctions
            self.projectLayerList['tmp_vertice_table_junctions'] = args['tmp_vertice_table_junctions']
            
            
            # Save layer as DPs
            vl_dps = self.iface.addVectorLayer(uri.uri(), args['tmp_vertice_table_dps'], db.getProviderName())  
            if not vl_dps:
                QMessageBox.information(self.dockwidget, self.dockwidget.windowTitle(), 'Invalid Layer:\n - No paths found or\n - Failed to create vector layer from query')
            vl_dps.loadNamedStyle(plugin_path + '/assets/styles/route_dps.qml')
            self.projectLayerList['vertice_dps_psql'] = vl_dps
            self.projectLayerList['tmp_vertice_table_dps'] = args['tmp_vertice_table_dps']  
            
            
            # Save any pnt to be shown as location
            uri_any = db.getURI()     
            uri_any.setDataSource(args['results_schema'], args['tmp_vertice_table'], "geom", "seq = 10", "seq")     #path_geom holds route segments in correct subsequent order != geom
            vl_any = self.iface.addVectorLayer(uri_any.uri(), args['tmp_vertice_table_any'], db.getProviderName())  
            if not vl_any:
                QMessageBox.information(self.dockwidget, self.dockwidget.windowTitle(), 'Invalid Layer:\n - No paths found or\n - Failed to create vector layer from query')
            vl_any.loadNamedStyle(plugin_path + '/assets/styles/route_pnt.qml')
            self.projectLayerList['vertice_any_psql'] = vl_any
            self.projectLayerList['tmp_vertice_table_any'] = args['tmp_vertice_table_any']
            
            
            self.moveAnalyzedRoute()
            
        except psycopg2.DatabaseError, e:
            print "** Database Error"
            if str(e).__contains__("my_route_get_dp"):
                print "function does not exist error"
                #create function
                self.createMissingFkt("my_route_get_dp")
                
                #run bufferNetwork() again
                self.dockwidget.btnAnalyzeRoute.click()
            else:  
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

        stop = timeit.default_timer()
        print('analyzeRoute time: ', stop - start)
        

    def getEnvironmentalRegions(self):
        """Retrieve urban areas from the OpenNRW dataset within sepcified buffer around the route.
        
        """
        
        print "** getEnvironmentalRegions"
        
        start = timeit.default_timer()
                
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
            
            args['tmp_route_table'] = self.projectLayerList['tmp_route_table']
            args['urban_areas'] = 'urban_areas'
            args['urban_labels'] = 'urban_labels'
            
            #SQL Query
            # SELECT * FROM %(results_schema)s.%(tmp_route_table)s
            query = """DROP TABLE IF EXISTS %(results_schema)s.%(urban_areas)s;
                SELECT * INTO %(results_schema)s.%(urban_areas)s
                FROM my_regions_route_intersect_buffer('%(open_nrw_schema)s.%(open_nrw_dlm)s', '%(results_schema)s.%(tmp_route_table)s', 
                    ((SELECT sum(km) FROM %(results_schema)s.%(tmp_route_table)s)*1000));
                ALTER TABLE %(results_schema)s.%(urban_areas)s ADD COLUMN shape_length numeric, ADD COLUMN shape_area numeric;
                UPDATE %(results_schema)s.%(urban_areas)s SET shape_length=ST_Perimeter(geom), shape_area=ST_Area(geom);
                UPDATE %(results_schema)s.%(urban_areas)s as t SET geom = a.geom FROM
                    (SELECT id, ST_Collect(ST_MakePolygon(geom)) As geom
                    FROM (SELECT id, ST_ExteriorRing((ST_Dump(geom)).geom) As geom FROM %(results_schema)s.%(urban_areas)s) as s
                    GROUP BY id) as a
                    WHERE t.id = a.id;""" % args
                            
            #QMessageBox.information(self.dockwidget, self.dockwidget.windowTitle(),query)
            print "getEnvironmentalRegions query: " + query
            
            Utils.logMessage('Query:\n' + query)
            cur.execute(self.cleanQuery(query))
            con.commit()
            
            
            # Urban areas
            uri = db.getURI()     
            uri.setDataSource(args['results_schema'], args['urban_areas'], "geom", "", "id")     #path_geom holds route segments in correct subsequent order != geom
            vl = self.iface.addVectorLayer(uri.uri(), args['urban_areas'], db.getProviderName())  
            if not vl:
                QMessageBox.information(self.dockwidget, self.dockwidget.windowTitle(), 'Invalid Layer:\n - No paths found or\n - Failed to create vector layer from query')
            vl.loadNamedStyle(plugin_path + '/assets/styles/urban_areas.qml')
            self.projectLayerList['urban_areas_psql'] = vl
            self.projectLayerList['urban_areas'] = args['urban_areas']
            
            # Urban labels 
            vl_labels = self.iface.addVectorLayer(uri.uri(), args['urban_labels'], db.getProviderName())  
            if not vl_labels:
                QMessageBox.information(self.dockwidget, self.dockwidget.windowTitle(), 'Invalid Layer:\n - No paths found or\n - Failed to create vector layer from query')
            vl_labels.loadNamedStyle(plugin_path + '/assets/styles/urban_labels.qml')
            self.projectLayerList['urban_labels_psql'] = vl_labels
            self.projectLayerList['urban_labels'] = args['urban_labels']
            
            self.moveEnvironmentalRegions()
            
            
        except psycopg2.DatabaseError, e:
            print "** Database Error"
            if str(e).__contains__("my_regions_route_intersect_buffer"):
                print "function does not exist error"
                #create function
                self.createMissingFkt("my_regions_route_intersect_buffer")
                
                #run bufferNetwork() again
                self.dockwidget.btnGetEnvironmentalRegions.click()
            else:  
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
        
        stop = timeit.default_timer()
        print('getEnvironmentalRegions time: ', stop - start)
        
    
    def addRegionsNetwork(self):
        """Merge network within the regions into the network dataset.
        
        """
        
        print "** addRegionsNetwork"
        
        start = timeit.default_timer()
                
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
            
            args['tmp_route_table'] = self.projectLayerList['tmp_route_table']
            args['edge_table_buffered'] = self.projectLayerList['edge_table_buffered']
            args['urban_areas'] = self.projectLayerList['urban_areas']
            
            
            #SQL Query
            query = """INSERT INTO %(results_schema)s.%(edge_table_buffered)s
                SELECT s.* FROM
                    %(edge_schema)s.%(edge_table)s s, %(results_schema)s.%(urban_areas)s r
                    WHERE ST_Intersects(ST_Transform(s.geom, 25832), r.geom) AND 
                        s.id not in (SELECT id FROM %(results_schema)s.%(edge_table_buffered)s)""" % args
                
            print "addRegionsNetwork query: " + query
                
            Utils.logMessage('Query:\n' + query)
            cur.execute(self.cleanQuery(query))
            con.commit()
            
            
            self.projectLayerList['buffered_network_psql'].triggerRepaint()
            
            
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
        
        stop = timeit.default_timer()
        print('addRegionsNetwork time: ', stop - start)

    
    def getAdministrativeRegions(self):
        """getAdministrativeRegions
        
        """
        
        print "** getAdministrativeRegions"
        
        start = timeit.default_timer()
        
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
            
            args['tmp_route_table'] = self.projectLayerList['tmp_route_table']
            args['adminlevel_9'] = 'adminlevel_9'
            args['adminlevel_10'] = 'adminlevel_10'
            args['adminlevel_11'] = 'adminlevel_11'
            
            #SQL Query
            query = """DROP TABLE IF EXISTS %(results_schema)s.%(adminlevel_9)s;
                WITH lines as (
                    SELECT DISTINCT ON (osm_id) osm_id, name, ST_LineMerge(way) as way FROM %(osm_schema)s.%(osm_lines)s WHERE boundary = 'administrative' AND admin_level = '9' AND ST_IsClosed(way) GROUP BY osm_id,way,name
                )
                SELECT osm_id, name, ST_MakePolygon(way) as geom INTO %(results_schema)s.tmp FROM lines;
                SELECT * INTO %(results_schema)s.%(adminlevel_9)s FROM my_admin_regions_route_intersect_buffer('%(results_schema)s.tmp', '%(results_schema)s.%(tmp_route_table)s', ((SELECT sum(km) FROM %(results_schema)s.%(tmp_route_table)s)*1000)) a;
                DROP TABLE IF EXISTS %(results_schema)s.tmp;
                
                DROP TABLE IF EXISTS %(results_schema)s.%(adminlevel_10)s;
                WITH lines as (
                    SELECT DISTINCT ON (osm_id) osm_id, name, ST_LineMerge(way) as way FROM %(osm_schema)s.%(osm_lines)s WHERE boundary = 'administrative' AND admin_level = '10' AND ST_IsClosed(way) GROUP BY osm_id,way,name
                )
                SELECT osm_id, name, ST_MakePolygon(way) as geom INTO %(results_schema)s.tmp FROM lines;
                SELECT * INTO %(results_schema)s.%(adminlevel_10)s FROM my_admin_regions_route_intersect_buffer('%(results_schema)s.tmp', '%(results_schema)s.%(tmp_route_table)s', ((SELECT sum(km) FROM %(results_schema)s.%(tmp_route_table)s)*1000)) a;
                DROP TABLE IF EXISTS %(results_schema)s.tmp;
                
                DROP TABLE IF EXISTS %(results_schema)s.%(adminlevel_11)s;
                WITH lines as (
                    SELECT DISTINCT ON (osm_id) osm_id, name, ST_LineMerge(way) as way FROM %(osm_schema)s.%(osm_lines)s WHERE boundary = 'administrative' AND admin_level = '11' AND ST_IsClosed(way) GROUP BY osm_id,way,name
                )
                SELECT osm_id, name, ST_MakePolygon(way) as geom INTO %(results_schema)s.tmp FROM lines;
                SELECT * INTO %(results_schema)s.%(adminlevel_11)s FROM my_admin_regions_route_intersect_buffer('%(results_schema)s.tmp', '%(results_schema)s.%(tmp_route_table)s', ((SELECT sum(km) FROM %(results_schema)s.%(tmp_route_table)s)*1000)) a;
                DROP TABLE IF EXISTS %(results_schema)s.tmp;""" % args
                
            print "getAdministrativeRegions query: " + query
            
            Utils.logMessage('Query:\n' + query)
            cur.execute(self.cleanQuery(query))
            con.commit()
            
            
            # Adminlevel 9
            uri = db.getURI()     
            uri.setDataSource(args['results_schema'], args['adminlevel_9'], "geom", "", "seq")     #path_geom holds route segments in correct subsequent order != geom
            vl = self.iface.addVectorLayer(uri.uri(), args['adminlevel_9'], db.getProviderName())  
            if not vl:
                QMessageBox.information(self.dockwidget, self.dockwidget.windowTitle(), 'Invalid Layer:\n - No paths found or\n - Failed to create vector layer from query')
            else:
                vl.loadNamedStyle(plugin_path + '/assets/styles/administrative/gem.qml')
                self.projectLayerList['adminlevel_9_psql'] = vl
                self.projectLayerList['adminlevel_9'] = args['adminlevel_9']
            
            # Adminlevel 10
            uri = db.getURI()     
            uri.setDataSource(args['results_schema'], args['adminlevel_10'], "geom", "", "seq")     #path_geom holds route segments in correct subsequent order != geom
            vl = self.iface.addVectorLayer(uri.uri(), args['adminlevel_10'], db.getProviderName())  
            if not vl:
                QMessageBox.information(self.dockwidget, self.dockwidget.windowTitle(), 'Invalid Layer:\n - No paths found or\n - Failed to create vector layer from query')
            else:
                vl.loadNamedStyle(plugin_path + '/assets/styles/administrative/gem.qml')
                self.projectLayerList['adminlevel_10_psql'] = vl
                self.projectLayerList['adminlevel_10'] = args['adminlevel_10']
            
            # Adminlevel 11
            uri = db.getURI()     
            uri.setDataSource(args['results_schema'], args['adminlevel_11'], "geom", "", "seq")     #path_geom holds route segments in correct subsequent order != geom
            vl = self.iface.addVectorLayer(uri.uri(), args['adminlevel_11'], db.getProviderName())  
            if not vl:
                QMessageBox.information(self.dockwidget, self.dockwidget.windowTitle(), 'Invalid Layer:\n - No paths found or\n - Failed to create vector layer from query')
            else:
                vl.loadNamedStyle(plugin_path + '/assets/styles/administrative/gem.qml')
                self.projectLayerList['adminlevel_11_psql'] = vl
                self.projectLayerList['adminlevel_11'] = args['adminlevel_11']
                
            self.moveAdministrativeRegions()
            
            
        except psycopg2.DatabaseError, e:
            print "** Database Error"
            if str(e).__contains__("my_admin_regions_route_intersect_buffer"):
                print "function does not exist error"
                #create function
                self.createMissingFkt("my_admin_regions_route_intersect_buffer")
                
                #run bufferNetwork() again
                self.dockwidget.btnGetAdministrativeRegions.click()
            else:  
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
                  
        stop = timeit.default_timer()
        print('getAdministrativeRegions time: ', stop - start)

  
    def genericDatabaseFunction(self):
        """Generic function with basic code for every function processing the datbase
        
        """
        
        print "** genericDatabaseFunction"
        
        start = timeit.default_timer()
        
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
            
            args['tmp_route_table'] = self.projectLayerList['tmp_route_table']
            
            #SQL Query
            query = """SELECT * FROM %(results_schema)s.%(tmp_route_table)s""" % args
                
                
            Utils.logMessage('Query:\n' + query)
            cur.execute(self.cleanQuery(query))
            con.commit()
            
            
            # Specify tmp table in uri
            uri = db.getURI()     
            uri.setDataSource(args['results_schema'], args['tmp_route_table'], "geom", "", "seq")     #path_geom holds route segments in correct subsequent order != geom
            
            
            # Save layer as junctions
            vl = self.iface.addVectorLayer(uri.uri(), args['tmp_vertice_table_junctions'], db.getProviderName())  
            if not vl:
                QMessageBox.information(self.dockwidget, self.dockwidget.windowTitle(), 'Invalid Layer:\n - No paths found or\n - Failed to create vector layer from query')
            vl.loadNamedStyle(plugin_path + '/assets/styles/route.qml')
            self.projectLayerList['route_table_psql'] = vl
            self.projectLayerList['tmp_route_table'] = args['tmp_route_table']
            
            
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
        
        stop = timeit.default_timer()
        print('genericDatabaseFunction time: ', stop - start)
        
        
    def createMissingFkt(self, fkt):
        """Create function not existing sql function.
        
        """
        
        print "** createFktBufferNetwork"
        
        start = timeit.default_timer()
        
        db = None
        try:
            dbname = str(self.dockwidget.comboBoxDatabase.currentText())            
            db = self.connectionsDB[dbname].connect()
            con = db.con
            cur = con.cursor()
            
            query = Utils.getMissingFktQuery(fkt)
            
            print "createMissingFkt: " + query
            
            Utils.logMessage('create missing function:\n' + query)
            cur.execute(self.cleanQuery(query))
            con.commit()          
            
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
        
        stop = timeit.default_timer()
        print('createFktBufferNetwork time: ', stop - start)


    # --------------------------------------------------------------------------
    # Helping Functions
    
        
    def moveRouteLayers(self):
        
        print "** moveRouteLayers"
        # Route
        node = self.projectLayerPanel['root'].findLayer(self.projectLayerList['route_psql'].id())
        node_clone = node.clone()
        self.projectLayerPanel['route'].insertChildNode(0,node_clone)
        self.projectLayerPanel['root'].removeChildNode(node)
        
        # Vertices
        node = self.projectLayerPanel['root'].findLayer(self.projectLayerList['vertice_psql'].id())
        node_clone = node.clone()
        node_clone.setVisible(Qt.Unchecked)
        self.projectLayerPanel['route'].insertChildNode(0,node_clone)
        self.projectLayerPanel['root'].removeChildNode(node)
        
        # Start
        node = self.projectLayerPanel['root'].findLayer(self.projectLayerList['vertice_start_psql'].id())
        node_clone = node.clone()
        node_clone.setExpanded(False)
        self.projectLayerPanel['route'].insertChildNode(0,node_clone)
        self.projectLayerPanel['root'].removeChildNode(node)
        
        # End
        node = self.projectLayerPanel['root'].findLayer(self.projectLayerList['vertice_end_psql'].id())
        node_clone = node.clone()
        node_clone.setExpanded(False)
        self.projectLayerPanel['route'].insertChildNode(0,node_clone)
        self.projectLayerPanel['root'].removeChildNode(node)
        
    def moveBufferLayer(self):
        
        print "** moveBufferLayer"
        
        node = self.projectLayerPanel['root'].findLayer(self.projectLayerList['buffered_network_psql'].id())
        node_clone = node.clone()
        self.projectLayerPanel['network_selection'].insertChildNode(0,node_clone)
        self.projectLayerPanel['root'].removeChildNode(node)
        self.projectLayerPanel['default'].removeChildNode(node)
        
    def moveAnalyzedRoute(self):
        
        print "** moveAnalyzedRoute"
        
        # Junctions
        node = self.projectLayerPanel['root'].findLayer(self.projectLayerList['vertice_junctions_psql'].id())
        node_clone = node.clone()
        node_clone.setExpanded(False)
        node_clone.setVisible(Qt.Unchecked)
        self.projectLayerPanel['route'].insertChildNode(2,node_clone)
        self.projectLayerPanel['root'].removeChildNode(node)
        
        # DPs
        node = self.projectLayerPanel['root'].findLayer(self.projectLayerList['vertice_dps_psql'].id())
        node_clone = node.clone()
        node_clone.setExpanded(False)
        self.projectLayerPanel['route'].insertChildNode(2,node_clone)
        self.projectLayerPanel['root'].removeChildNode(node)
        
        # Any pnt
        node = self.projectLayerPanel['root'].findLayer(self.projectLayerList['vertice_any_psql'].id())
        node_clone = node.clone()
        node_clone.setExpanded(False)
        self.projectLayerPanel['route'].insertChildNode(0,node_clone)
        self.projectLayerPanel['root'].removeChildNode(node)
        
    def moveEnvironmentalRegions(self):
        
        print "** moveEnvironmentalRegions"
        
        # Urban areas
        node = self.projectLayerPanel['root'].findLayer(self.projectLayerList['urban_areas_psql'].id())
        node_clone = node.clone()
        node_clone.setExpanded(False)
        self.projectLayerPanel['environmental_regions'].insertChildNode(0,node_clone)
        self.projectLayerPanel['root'].removeChildNode(node)
        self.projectLayerPanel['default'].removeChildNode(node)
        
        # Urban labels
        node = self.projectLayerPanel['root'].findLayer(self.projectLayerList['urban_labels_psql'].id())
        node_clone = node.clone()
        node_clone.setExpanded(False)
        self.projectLayerPanel['environmental_regions'].insertChildNode(0,node_clone)
        self.projectLayerPanel['root'].removeChildNode(node)
        self.projectLayerPanel['default'].removeChildNode(node)        
        
    def moveAdministrativeRegions(self):
        
        print "** moveEnvironmentalRegions"
        
        # Adminlevel 9
        if 'adminlevel_9_psql' in self.projectLayerList.keys():
            node = self.projectLayerPanel['root'].findLayer(self.projectLayerList['adminlevel_9_psql'].id())
            node_clone = node.clone()
            node_clone.setExpanded(False)
            self.projectLayerPanel['administrative_regions'].insertChildNode(0,node_clone)
            self.projectLayerPanel['root'].removeChildNode(node)
            self.projectLayerPanel['default'].removeChildNode(node)
        
        # Adminlevel 10
        if 'adminlevel_10_psql' in self.projectLayerList.keys():
            node = self.projectLayerPanel['root'].findLayer(self.projectLayerList['adminlevel_10_psql'].id())
            node_clone = node.clone()
            node_clone.setExpanded(False)
            self.projectLayerPanel['administrative_regions'].insertChildNode(0,node_clone)
            self.projectLayerPanel['root'].removeChildNode(node)
            self.projectLayerPanel['default'].removeChildNode(node)
        
        # Adminlevel 11
        if 'adminlevel_11_psql' in self.projectLayerList.keys():
            node = self.projectLayerPanel['root'].findLayer(self.projectLayerList['adminlevel_11_psql'].id())
            node_clone = node.clone()
            node_clone.setExpanded(False)
            self.projectLayerPanel['administrative_regions'].insertChildNode(0,node_clone)
            self.projectLayerPanel['root'].removeChildNode(node)
            self.projectLayerPanel['default'].removeChildNode(node)
        
        
    def checkDP(self):
        """Check if Vertice is a DP.
        
        ToDos:
            1.) Retrieves Vertice + all connecting street segments with incoming and outgoing route.
            2.) Case decision:
                - degree 2 with angle larger than [45]° --> turn not at a junction [2]
                - degree 3 with turn (specific angles?) --> turn at a t-junction [3]
                - streets part of roundabout --> turn at a roundabout [5]
                    (this will probable affect next DPs)
                - degree 4 with route straight and same or higher class --> straight on [1]
                - degree >= 4 with route not straight --> turn at junction [4]
        
                - class highway + exit (TODO) --> exit [6]
        """
        
        print "** checkDP"
        
        

    def cleanQuery(self, msgQuery):
        query = msgQuery.replace('\n', ' ')
        query = re.sub(r'\s+', ' ', query)
        query = query.replace('( ', '(')
        query = query.replace(' )', ')')
        query = query.strip()
        return query
    
    def toggleSelectButton(self, button):
        selectButtons = [
            self.dockwidget.btnSelectSourceID,
            self.dockwidget.btnSelectTargetID
        ]
        for selectButton in selectButtons:
            if selectButton != button:
                if selectButton.isChecked():
                    selectButton.click()
                    
    
    def getArguments(self, controls):
        args = {}       #'dict'
        
        if 'comboBoxResultsSchema' in controls:
            args['results_schema'] = self.dockwidget.comboBoxResultsSchema.currentText()
        if 'comboBoxEdgesSchema' in controls:
            args['edge_schema'] = self.dockwidget.comboBoxEdgesSchema.currentText()
        if 'comboBoxEdgesTable' in controls:
            args['edge_table'] = self.dockwidget.comboBoxEdgesTable.currentText()
        if 'comboBoxVerticesTable' in controls:
            args['vertice_table'] = self.dockwidget.comboBoxVerticesTable.currentText()
        #if 'comboBoxRouteTable' in controls:
            #args['tmp_route_table'] = self.dockwidget.comboBoxRouteTable.currentText()    
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

        if 'lineEditMaxClazz' in controls:
            args['max_clazz'] = self.dockwidget.lineEditMaxClazz.text()
            
        if 'lineEditApproxRndDist' in controls:
            args['approx_rnd_dist'] = self.dockwidget.lineEditApproxRndDist.text()
            
        if 'checkBoxWithinApproxRndDist' in controls:
            args['within_approx_rnd_dist'] = str(self.dockwidget.checkBoxWithinApproxRndDist.isChecked()).lower()
            
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
        
        
        # OPEN NRW
        if 'comboBoxOpenNRWSchema' in controls:
            args['open_nrw_schema'] = self.dockwidget.comboBoxOpenNRWSchema.currentText()
        if 'comboBoxOpenNRWDLM' in controls:
            args['open_nrw_dlm'] = self.dockwidget.comboBoxOpenNRWDLM.currentText() 
            
        
        # OSM
        if 'comboBoxOSMSchema' in controls:
            args['osm_schema'] = self.dockwidget.comboBoxOSMSchema.currentText()
        if 'comboBoxOSMPointsTable' in controls:
            args['osm_points'] = self.dockwidget.comboBoxOSMPointsTable.currentText() 
        if 'comboBoxOSMLinesTable' in controls:
            args['osm_lines'] = self.dockwidget.comboBoxOSMLinesTable.currentText() 
        if 'comboBoxOSMPolygonsTable' in controls:
            args['osm_polygons'] = self.dockwidget.comboBoxOSMPolygonsTable.currentText() 
            
        
        return args        
    
    
    def setDefaultArguments(self, controls):
        """Loads default arguments and fills the widget boxes with the labels"""
        
        oldReloadMessage = self.reloadMessage
        self.reloadMessage = False
        
        #comboBoxDatabase
        idx = self.dockwidget.comboBoxDatabase.findText('postgres')
        if idx >= 0:
            self.dockwidget.comboBoxDatabase.setCurrentIndex(idx) #reset to previous selection
        else:
            self.dockwidget.comboBoxDatabase.setCurrentIndex(0)
        self.reloadMessage = oldReloadMessage

        #comboBoxResultsSchema
        idx = self.dockwidget.comboBoxResultsSchema.findText('tmp')
        if idx >= 0:
            self.dockwidget.comboBoxResultsSchema.setCurrentIndex(idx) #reset to previous selection
        else:
            self.dockwidget.comboBoxResultsSchema.setCurrentIndex(0)
            
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
            
        #comboBoxRoutesTable > no default
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
 
        if 'lineEditMaxClazz' in controls:
            self.dockwidget.lineEditMaxClazz.setText('50')
            #self.dockwidget.lineEditSelectSourceID.insert(self.getRandomID())
            
        if 'lineEditApproxRndDist' in controls:
            self.dockwidget.lineEditApproxRndDist.setText('10')
            
        if 'checkBoxWithinApproxRndDist' in controls:
            self.dockwidget.checkBoxWithinApproxRndDist.setChecked(False)
            
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
            
            
        #comboBoxOpenNRWSchema
        idx = self.dockwidget.comboBoxOpenNRWSchema.findText('open_nrw')
        if idx >= 0:
            self.dockwidget.comboBoxOpenNRWSchema.setCurrentIndex(idx) #reset to previous selection
        else:
            self.dockwidget.comboBoxOpenNRWSchema.setCurrentIndex(0)
            
        #comboBoxOpenNRWDLM
        idx = self.dockwidget.comboBoxOpenNRWDLM.findText('dlm250_sie01_f')
        if idx >= 0:
            self.dockwidget.comboBoxOpenNRWDLM.setCurrentIndex(idx) #reset to previous selection
        else:
            self.dockwidget.comboBoxOpenNRWDLM.setCurrentIndex(0)
            
            
        #OSM
        idx = self.dockwidget.comboBoxOSMSchema.findText('mland_osm2pgsql')
        if idx >= 0:
            self.dockwidget.comboBoxOSMSchema.setCurrentIndex(idx) #reset to previous selection
        else:
            self.dockwidget.comboBoxOSMSchema.setCurrentIndex(0)
            
        idx = self.dockwidget.comboBoxOSMPointsTable.findText('planet_osm_point')
        if idx >= 0:
            self.dockwidget.comboBoxOSMPointsTable.setCurrentIndex(idx) #reset to previous selection
        else:
            self.dockwidget.comboBoxOSMPointsTable.setCurrentIndex(0)
            
        idx = self.dockwidget.comboBoxOSMLinesTable.findText('planet_osm_line')
        if idx >= 0:
            self.dockwidget.comboBoxOSMLinesTable.setCurrentIndex(idx) #reset to previous selection
        else:
            self.dockwidget.comboBoxOSMLinesTable.setCurrentIndex(0)
            
        idx = self.dockwidget.comboBoxOSMPolygonsTable.findText('planet_osm_polygon')
        if idx >= 0:
            self.dockwidget.comboBoxOSMPolygonsTable.setCurrentIndex(idx) #reset to previous selection
        else:
            self.dockwidget.comboBoxOSMPolygonsTable.setCurrentIndex(0)
    
    
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
    
    def selectSourceId(self, checked):
        if checked:
            self.toggleSelectButton(self.dockwidget.btnSelectSourceID)
            self.dockwidget.lineEditSelectSourceID.setText("")
            self.sourceIdVertexMarker.setVisible(False)
            self.sourceIdRubberBand.reset(Utils.getRubberBandType(False))
            self.iface.mapCanvas().setMapTool(self.sourceIdEmitPoint)
        else:
            self.iface.mapCanvas().unsetMapTool(self.sourceIdEmitPoint)
    
    def setSourceId(self, pt):
        function = self.functions['dijkstra']
        args = self.getArguments(function.getControlNames(self.version))
        if not function.isEdgeBase():
            result, id, wkt = self.findNearestNode(args, pt)
            if result:
                self.dockwidget.lineEditSelectSourceID.setText(str(id))
                geom = QgsGeometry().fromWkt(wkt)
                self.sourceIdVertexMarker.setCenter(geom.asPoint())
                self.sourceIdVertexMarker.setVisible(True)
                self.dockwidget.btnSelectSourceID.click()
        else:
            QMessageBox.information(self.dockwidget, self.dockwidget.windowTitle(), 'isEdgeBase.')
        Utils.refreshMapCanvas(self.iface.mapCanvas())
            
    def selectTargetId(self, checked):
        if checked:
            self.toggleSelectButton(self.dockwidget.btnSelectTargetID)
            self.dockwidget.lineEditSelectTargetID.setText("")
            self.targetIdVertexMarker.setVisible(False)
            self.targetIdRubberBand.reset(Utils.getRubberBandType(False))
            self.iface.mapCanvas().setMapTool(self.targetIdEmitPoint)
        else:
            self.iface.mapCanvas().unsetMapTool(self.targetIdEmitPoint)
            
    def setTargetId(self, pt):
        function = self.functions['dijkstra']
        args = self.getArguments(function.getControlNames(self.version))
        if not function.isEdgeBase():
            ## TODO implement findNearestNode function
            result, id, wkt = self.findNearestNode(args, pt)
            if result:
                self.dockwidget.lineEditSelectTargetID.setText(str(id))
                geom = QgsGeometry().fromWkt(wkt)
                self.targetIdVertexMarker.setCenter(geom.asPoint())
                self.targetIdVertexMarker.setVisible(True)
                self.dockwidget.btnSelectTargetID.click()
        else:
            QMessageBox.information(self.dockwidget, self.dockwidget.windowTitle(), 'isEdgeBase.')
        Utils.refreshMapCanvas(self.iface.mapCanvas())
        
            
    def setRandomSourceId(self):
        function = self.functions['dijkstra']
        args = self.getArguments(function.getControlNames(self.version))
        if not function.isEdgeBase():
            result, id, wkt = self.findRandomNode(args)
            if result:
                self.dockwidget.lineEditSelectSourceID.setText(str(id))
                geom = QgsGeometry().fromWkt(wkt)
                self.sourceIdVertexMarker.setCenter(geom.asPoint())
                self.sourceIdVertexMarker.setVisible(True)
        else:
            QMessageBox.information(self.dockwidget, self.dockwidget.windowTitle(), 'isEdgeBase.')
        Utils.refreshMapCanvas(self.iface.mapCanvas())
        
        
    def setRandomTargetId(self):
        function = self.functions['dijkstra']
        args = self.getArguments(function.getControlNames(self.version))
        if not function.isEdgeBase():            
            if self.dockwidget.checkBoxWithinApproxRndDist.isChecked():
                result, id, wkt = self.findRandomNodeWithinDist(args)
            else:
                result, id, wkt = self.findRandomNode(args)
            if result:
                self.dockwidget.lineEditSelectTargetID.setText(str(id))
                geom = QgsGeometry().fromWkt(wkt)
                self.targetIdVertexMarker.setCenter(geom.asPoint())
                self.targetIdVertexMarker.setVisible(True)
        else:
            QMessageBox.information(self.dockwidget, self.dockwidget.windowTitle(), 'isEdgeBase.')
        Utils.refreshMapCanvas(self.iface.mapCanvas())
        
            
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


    def findNearestNode(self, args, pt):
        distance = self.iface.mapCanvas().getCoordinateTransform().mapUnitsPerPixel() * self.FIND_RADIUS
        rect = QgsRectangle(pt.x() - distance, pt.y() - distance, pt.x() + distance, pt.y() + distance)
        canvasCrs = Utils.getDestinationCrs(self.iface.mapCanvas())
        db = None
        try:
            dbname = str(self.dockwidget.comboBoxDatabase.currentText())            
            db = self.connectionsDB[dbname].connect()
            con = db.con
            
            #srid, geomType = self.getSridAndGeomType(con, args)
            #srid, geomType = Utils.getSridAndGeomType(con, args['edge_table'], args['geometry'])
            
            #srid, geomType = Utils.getSridAndGeomType(con, '%(edge_table)s' % args, '%(geometry)s' % args)
            srid, geomType = Utils.getSridAndGeomType(con, args)
            if self.iface.mapCanvas().hasCrsTransformEnabled():
                layerCrs = QgsCoordinateReferenceSystem()
                Utils.createFromSrid(layerCrs, srid)
                trans = QgsCoordinateTransform(canvasCrs, layerCrs)
                pt = trans.transform(pt)
                rect = trans.transform(rect)
            
            args['canvas_srid'] = Utils.getCanvasSrid(canvasCrs)
            args['srid'] = srid
            args['x'] = pt.x()
            args['y'] = pt.y()
            args['minx'] = rect.xMinimum()
            args['miny'] = rect.yMinimum()
            args['maxx'] = rect.xMaximum()
            args['maxy'] = rect.yMaximum()
            
            args['clazz'] = 'clazz'
            
            Utils.setStartPoint(geomType, args)
            Utils.setEndPoint(geomType, args)
            #Utils.setTransformQuotes(args)
            Utils.setTransformQuotes(args, srid, args['canvas_srid'])
            
            # Getting nearest source
            query1 = """
                SELECT e.%(source)s,
                ST_Distance(
                    v.geom,
                    ST_GeomFromText('POINT(%(x)f %(y)f)', %(srid)d)
                ) AS dist,
                ST_AsText(%(transform_s)s v.geom %(transform_e)s)
                FROM %(edge_schema)s.%(vertice_table)s as v, %(edge_schema)s.%(edge_table)s as e
                WHERE
                    v.id = e.%(source)s AND e.clazz <= %(max_clazz)s
                    ORDER BY v.geom <-> ST_SetSRID(ST_Point(%(x)f, %(y)f), %(srid)d) LIMIT 1""" % args
                    
            #QMessageBox.critical(self.dockwidget, self.dockwidget.windowTitle(), '%s' % query1)
            
            ##Utils.logMessage(query1)
            cur1 = con.cursor()
            cur1.execute(query1)
            row1 = cur1.fetchone()
            d1 = None
            source = None
            wkt1 = None
            if row1:
                d1 = row1[1]
                source = row1[0]
                wkt1 = row1[2]
            
            # Getting nearest target
            query2 = """
                SELECT e.%(target)s,
                ST_Distance(
                    v.geom,
                    ST_GeomFromText('POINT(%(x)f %(y)f)', %(srid)d)
                ) AS dist,
                ST_AsText(%(transform_s)s v.geom %(transform_e)s)
                FROM %(edge_schema)s.%(vertice_table)s as v, %(edge_schema)s.%(edge_table)s as e
                WHERE
                    v.id = e.%(target)s AND e.clazz <= %(max_clazz)s
                    ORDER BY v.geom <-> ST_SetSRID(ST_Point(%(x)f, %(y)f), %(srid)d) LIMIT 1""" % args
                    
            #QMessageBox.critical(self.dockwidget, self.dockwidget.windowTitle(), '%s' % query2)
            
            ##Utils.logMessage(query2)
            cur2 = con.cursor()
            cur2.execute(query2)
            row2 = cur2.fetchone()
            d2 = None
            target = None
            wkt2 = None
            if row2:
                d2 = row2[1]
                target = row2[0]
                wkt2 = row2[2]
            
            # Checking what is nearer - source or target
            d = None
            node = None
            wkt = None
            if d1 and (not d2):
                node = source
                d = d1
                wkt = wkt1
            elif (not d1) and d2:
                node = target
                d = d2
                wkt = wkt2
            elif d1 and d2:
                if d1 < d2:
                    node = source
                    d = d1
                    wkt = wkt1
                else:
                    node = target
                    d = d2
                    wkt = wkt2
            
            ##Utils.logMessage(str(d))
            if (d == None) or (d > distance):
                node = None
                wkt = None
                return False, None, None
            
            return True, node, wkt
            
        except psycopg2.DatabaseError, e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self.dockwidget, self.dockwidget.windowTitle(), '%s' % e)
            return False, None, None
            
        finally:
            if db and db.con:
                db.con.close()
                
    
    def findRandomNode(self, args):
        
        print "** findRandomNode"
        
        canvasCrs = Utils.getDestinationCrs(self.iface.mapCanvas())
        db = None
        try:
            dbname = str(self.dockwidget.comboBoxDatabase.currentText())            
            db = self.connectionsDB[dbname].connect()
            con = db.con
            
            #srid, geomType = self.getSridAndGeomType(con, args)
            #srid, geomType = Utils.getSridAndGeomType(con, args['edge_table'], args['geometry'])
            
            #srid, geomType = Utils.getSridAndGeomType(con, '%(edge_table)s' % args, '%(geometry)s' % args)
            srid, geomType = Utils.getSridAndGeomType(con, args)
            if self.iface.mapCanvas().hasCrsTransformEnabled():
                layerCrs = QgsCoordinateReferenceSystem()
                Utils.createFromSrid(layerCrs, srid)
            
            args['canvas_srid'] = Utils.getCanvasSrid(canvasCrs)
            args['srid'] = srid
            args['clazz'] = 'clazz'
            
            Utils.setStartPoint(geomType, args)
            Utils.setEndPoint(geomType, args)
            #Utils.setTransformQuotes(args)
            Utils.setTransformQuotes(args, srid, args['canvas_srid'])
            
            # Getting nearest source
            query = """
                SELECT e.%(source)s,
                ST_AsText(%(transform_s)s v.geom %(transform_e)s)
                FROM %(edge_schema)s.%(vertice_table)s as v, %(edge_schema)s.%(edge_table)s as e
                WHERE
                    v.id = e.%(source)s AND e.clazz <= %(max_clazz)s 
                    ORDER BY random()
                    LIMIT 1""" % args
                    
            #QMessageBox.critical(self.dockwidget, self.dockwidget.windowTitle(), '%s' % query)
            
            ##Utils.logMessage(query1)
            cur = con.cursor()
            cur.execute(query)
            row = cur.fetchone()
            node = None
            wkt = None
            if row:
                node = row[0]
                wkt = row[1]
            
            return True, node, wkt
            
        except psycopg2.DatabaseError, e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self.dockwidget, self.dockwidget.windowTitle(), '%s' % e)
            return False, None, None
            
        finally:
            if db and db.con:
                db.con.close()
                
                
    def findRandomNodeWithinDist(self, args):
        
        print "** findRandomNodeWithinDist" 
        
        canvasCrs = Utils.getDestinationCrs(self.iface.mapCanvas())
        db = None
        try:
            dbname = str(self.dockwidget.comboBoxDatabase.currentText())            
            db = self.connectionsDB[dbname].connect()
            con = db.con
            
            #srid, geomType = self.getSridAndGeomType(con, args)
            #srid, geomType = Utils.getSridAndGeomType(con, args['edge_table'], args['geometry'])
            
            #srid, geomType = Utils.getSridAndGeomType(con, '%(edge_table)s' % args, '%(geometry)s' % args)
            srid, geomType = Utils.getSridAndGeomType(con, args)
            if self.iface.mapCanvas().hasCrsTransformEnabled():
                layerCrs = QgsCoordinateReferenceSystem()
                Utils.createFromSrid(layerCrs, srid)
            
            args['canvas_srid'] = Utils.getCanvasSrid(canvasCrs)
            args['srid'] = srid
            args['clazz'] = 'clazz'
            
            Utils.setStartPoint(geomType, args)
            Utils.setEndPoint(geomType, args)
            #Utils.setTransformQuotes(args)
            Utils.setTransformQuotes(args, srid, args['canvas_srid'])
            
            args['approx_rnd_dist_min'] = str((int(args['approx_rnd_dist']) - 1)*1000)
            args['approx_rnd_dist_max'] = str((int(args['approx_rnd_dist']) + 1)*1000)
            
            # Getting nearest source
            query = """
                WITH source_node as (
                    SELECT *
                    FROM %(edge_schema)s.%(edge_table)s as e
                    WHERE e.%(source)s = %(source_id)s
                )
                SELECT v.id, ST_AsText(%(transform_s)s v.geom %(transform_e)s)
                FROM %(edge_schema)s.%(vertice_table)s as v, source_node as s
                WHERE
                    ST_Distance(v.geom::geography, s.geom::geography) >= %(approx_rnd_dist_min)s
                    AND
                    ST_Distance(v.geom::geography, s.geom::geography) <= %(approx_rnd_dist_max)s
                ORDER BY random()
                LIMIT 1""" % args
                    
            #QMessageBox.critical(self.dockwidget, self.dockwidget.windowTitle(), '%s' % query)
            
            ##Utils.logMessage(query1)
            cur = con.cursor()
            cur.execute(query)
            row = cur.fetchone()
            node = None
            wkt = None
            if row:
                node = row[0]
                wkt = row[1]
            
            return True, node, wkt
            
        except psycopg2.DatabaseError, e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self.dockwidget, self.dockwidget.windowTitle(), '%s' % e)
            return False, None, None
            
        finally:
            if db and db.con:
                db.con.close()
                

    def loadSettings(self):
        
        print "** loadSettings"
        
        settings = QSettings()
        idx = self.dockwidget.comboBoxDatabase.findText(Utils.getStringValue(settings, '/orientationMapsCreator/Database', ''))
        if idx >= 0:
            self.dockwidget.comboBoxDatabase.setCurrentIndex(idx)
        
        idx = self.dockwidget.comboBoxResultsSchema.findText(Utils.getStringValue(settings, '/orientationMapsCreator/results_schema', ''))
        if idx >= 0:
            self.dockwidget.comboBoxResultsSchema.setCurrentIndex(idx)
            
        idx = self.dockwidget.comboBoxEdgesSchema.findText(Utils.getStringValue(settings, '/orientationMapsCreator/edge_schema', ''))
        if idx >= 0:
            self.dockwidget.comboBoxEdgesSchema.setCurrentIndex(idx)
            
        idx = self.dockwidget.comboBoxEdgesTable.findText(Utils.getStringValue(settings, '/orientationMapsCreator/edges_table', ''))
        if idx >= 0:
            self.dockwidget.comboBoxEdgesTable.setCurrentIndex(idx)

        idx = self.dockwidget.comboBoxVerticesTable.findText(Utils.getStringValue(settings, '/orientationMapsCreator/vertices_table', ''))
        if idx >= 0:
            self.dockwidget.comboBoxVerticesTable.setCurrentIndex(idx)
            
        idx = self.dockwidget.comboBoxRouteTable.findText(Utils.getStringValue(settings, '/orientationMapsCreator/route_table', ''))
        if idx >= 0:
            self.dockwidget.comboBoxRouteTable.setCurrentIndex(idx)
        
        self.dockwidget.lineEditGeometryColumn.setText(Utils.getStringValue(settings, '/orientationMapsCreator/sql/geometry', 'geom'))
        self.dockwidget.lineEditIDColumn.setText(Utils.getStringValue(settings, '/orientationMapsCreator/sql/id', 'id'))
        self.dockwidget.lineEditSourceColumn.setText(Utils.getStringValue(settings, '/orientationMapsCreator/sql/source', 'source'))
        self.dockwidget.lineEditTargetColumn.setText(Utils.getStringValue(settings, '/orientationMapsCreator/sql/target', 'target'))
        self.dockwidget.lineEditCostColumn.setText(Utils.getStringValue(settings, '/orientationMapsCreator/sql/cost', 'cost'))
        self.dockwidget.lineEditReverseCostColumn.setText(Utils.getStringValue(settings, '/orientationMapsCreator/sql/reverse_cost', 'reverse_cost'))
        
        self.dockwidget.lineEditMaxClazz.setText(Utils.getStringValue(settings, '/orientationMapsCreator/max_clazz', '50'))
        self.dockwidget.lineEditApproxRndDist.setText(Utils.getStringValue(settings, '/orientationMapsCreator/approx_rnd_dist', '10'))
        self.dockwidget.lineEditSelectSourceID.setText(Utils.getStringValue(settings, '/orientationMapsCreator/source_id', '437021'))
        self.dockwidget.lineEditSelectTargetID.setText(Utils.getStringValue(settings, '/orientationMapsCreator/target_id', '366598'))

        self.dockwidget.checkBoxDirected.setChecked(Utils.getBoolValue(settings, '/orientationMapsCreator/directed', False))
        self.dockwidget.checkBoxHasReverseCost.setChecked(Utils.getBoolValue(settings, '/orientationMapsCreator/has_reverse_cost', False))
        self.dockwidget.checkBoxWithinApproxRndDist.setChecked(Utils.getBoolValue(settings, '/orientationMapsCreator/within_approx_rnd_dist', False))
        
        # OPEN NRW
        idx = self.dockwidget.comboBoxOpenNRWSchema.findText(Utils.getStringValue(settings, '/orientationMapsCreator/open_nrw_schema', ''))
        if idx >= 0:
            self.dockwidget.comboBoxOpenNRWSchema.setCurrentIndex(idx)
            
        idx = self.dockwidget.comboBoxOpenNRWDLM.findText(Utils.getStringValue(settings, '/orientationMapsCreator/open_nrw_dlm', ''))
        if idx >= 0:
            self.dockwidget.comboBoxOpenNRWDLM.setCurrentIndex(idx)
            
            
        # OSM
        idx = self.dockwidget.comboBoxOSMSchema.findText(Utils.getStringValue(settings, '/orientationMapsCreator/osm_schema', ''))
        if idx >= 0:
            self.dockwidget.comboBoxOSMSchema.setCurrentIndex(idx)
            
        idx = self.dockwidget.comboBoxOSMPointsTable.findText(Utils.getStringValue(settings, '/orientationMapsCreator/osm_points', ''))
        if idx >= 0:
            self.dockwidget.comboBoxOSMPointsTable.setCurrentIndex(idx)
            
        idx = self.dockwidget.comboBoxOSMLinesTable.findText(Utils.getStringValue(settings, '/orientationMapsCreator/osm_lines', ''))
        if idx >= 0:
            self.dockwidget.comboBoxOSMLinesTable.setCurrentIndex(idx)
            
        idx = self.dockwidget.comboBoxOSMPolygonsTable.findText(Utils.getStringValue(settings, '/orientationMapsCreator/osm_polygons', ''))
        if idx >= 0:
            self.dockwidget.comboBoxOSMPolygonsTable.setCurrentIndex(idx)
            
    def saveSettings(self):
        
        print "** saveSettings"
        
        settings = QSettings()
        settings.setValue('/orientationMapsCreator/Database', self.dockwidget.comboBoxDatabase.currentText())
        settings.setValue('/orientationMapsCreator/results_schema', self.dockwidget.comboBoxResultsSchema.currentText())
        settings.setValue('/orientationMapsCreator/edge_schema', self.dockwidget.comboBoxEdgesSchema.currentText())
        
        settings.setValue('/orientationMapsCreator/edges_table', self.dockwidget.comboBoxEdgesTable.currentText())
        settings.setValue('/orientationMapsCreator/vertices_table', self.dockwidget.comboBoxVerticesTable.currentText())
        settings.setValue('/orientationMapsCreator/route_table', self.dockwidget.comboBoxRouteTable.currentText())
        settings.setValue('/orientationMapsCreator/sql/geometry', self.dockwidget.lineEditGeometryColumn.text())

        settings.setValue('/orientationMapsCreator/sql/id', self.dockwidget.lineEditIDColumn.text())
        settings.setValue('/orientationMapsCreator/sql/source', self.dockwidget.lineEditSourceColumn.text())
        settings.setValue('/orientationMapsCreator/sql/target', self.dockwidget.lineEditTargetColumn.text())
        settings.setValue('/orientationMapsCreator/sql/cost', self.dockwidget.lineEditCostColumn.text())
        settings.setValue('/orientationMapsCreator/sql/reverse_cost', self.dockwidget.lineEditReverseCostColumn.text())

        settings.setValue('/orientationMapsCreator/max_clazz', self.dockwidget.lineEditMaxClazz.text())
        settings.setValue('/orientationMapsCreator/approx_rnd_dist', self.dockwidget.lineEditApproxRndDist.text())
        settings.setValue('/orientationMapsCreator/source_id', self.dockwidget.lineEditSelectSourceID.text())
        settings.setValue('/orientationMapsCreator/target_id', self.dockwidget.lineEditSelectTargetID.text())

        settings.setValue('/orientationMapsCreator/directed', self.dockwidget.checkBoxDirected.isChecked())
        settings.setValue('/orientationMapsCreator/has_reverse_cost', self.dockwidget.checkBoxHasReverseCost.isChecked())
        settings.setValue('/orientationMapsCreator/within_approx_rnd_dist', self.dockwidget.checkBoxWithinApproxRndDist.isChecked())
        
        # OPEN NRW
        settings.setValue('/orientationMapsCreator/open_nrw_schema', self.dockwidget.comboBoxOpenNRWSchema.currentText())
        settings.setValue('/orientationMapsCreator/open_nrw_dlm', self.dockwidget.comboBoxOpenNRWDLM.currentText())
        
        # OSM
        settings.setValue('/orientationMapsCreator/osm_schema', self.dockwidget.comboBoxOSMSchema.currentText())
        settings.setValue('/orientationMapsCreator/osm_points', self.dockwidget.comboBoxOSMPointsTable.currentText())
        settings.setValue('/orientationMapsCreator/osm_lines', self.dockwidget.comboBoxOSMLinesTable.currentText())
        settings.setValue('/orientationMapsCreator/osm_polygons', self.dockwidget.comboBoxOSMPolygonsTable.currentText())
        
        
    # --------------------------------------------------------------------------
    # Run
    
    def run(self):
        """Run method that loads and starts the plugin"""
        
        print "** run"   # this is executed when the widget/plugin is opened/activated
        
        if not self.pluginIsActive:
            self.pluginIsActive = True

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

