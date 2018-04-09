# -*- coding: utf-8 -*-
"""
/***************************************************************************
 orientationMapsCreator
                                 A QGIS plugin
 Tool to create orientation maps.
 
 based on "pgRouting Layer" plugin. Copyright 2011 by Anita Graser 
                              -------------------
        begin                : 2018-03-28
        git sha              : $Format:%H$
        copyright            : (C) 2018 by Heinrich Löwen
        email                : loewen.heinrich@uni-muenster.de
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from qgis.core import *
from qgis.gui import *
from orientationMapsCreator_dockwidget import orientationMapsCreatorDockWidget
import orientationMapsCreator_utils as Utils
import dbConnection
import os
import psycopg2     #DatabaseError

# Initialize Qt resources from file resources.py
import resources

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
#         QObject.connect(self.dockwidget.comboBoxEdgesSchema, SIGNAL("currentIndexChanged(const QString&)"), lambda: self.updateSchemaConnectionEnabled('comboBoxEdgesSchema'))
        #With the lambda it would be the generic form, but then the exec will not work any more in this function (in python 2.7)
        QObject.connect(self.dockwidget.comboBoxEdgesSchema, SIGNAL("currentIndexChanged(const QString&)"), self.updateEdgesSchemaConnectionEnabled)
        QObject.connect(self.dockwidget.comboBoxOSMSchema, SIGNAL("currentIndexChanged(const QString&)"), self.updateOSMSchemaConnectionEnabled)
        QObject.connect(self.dockwidget.comboBoxOpenNRWSchema, SIGNAL("currentIndexChanged(const QString&)"), self.updateOpenNRWSchemaConnectionEnabled)
        
        QObject.connect(self.dockwidget.btnPreviewRoute, SIGNAL("clicked()"), self.calculateRoute)
        QObject.connect(self.dockwidget.btnClearPreview, SIGNAL("clicked()"), self.clear)
         
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

        self.clear()
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
        
        print "** reloadConnections"

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
        self.updateDatabaseConnectionEnabled()
        
        
    def updateDatabaseConnectionEnabled(self):
        """Connect to selected Database"""

        print "** updateDatabaseConnectionEnabled"
        
        dbname = str(self.dockwidget.comboBoxDatabase.currentText())
        if dbname =='':
            return

        db = self.connectionsDB[dbname].connect()
        con = db.con
        self.version = Utils.getPgrVersion(con)     #save overall version of selected database connection
        if self.reloadMessage:
            QMessageBox.information(self.dockwidget, self.dockwidget.windowTitle(), 
                                    'Selected database: ' + dbname + '\npgRouting version: ' + str(self.version))

#         currentFunction = self.dockwidget.comboBoxFunction.currentText()
#         if currentFunction =='':
#             return
# 
#         self.loadFunctionsForVersion()
#         self.updateFunctionEnabled(currentFunction)
        
    def updateEdgesSchemaConnectionEnabled(self):
        """Show available Database Schemas for the selected Database"""

        print "** updateEdgesSchemaConnectionEnabled"
        #TODO
        
    def updateOSMSchemaConnectionEnabled(self):
        """Show available Database Schemas for the selected Database"""

        print "** updateOSMSchemaConnectionEnabled"
        #TODO
        
    def updateOpenNRWSchemaConnectionEnabled(self):
        """Show available Database Schemas for the selected Database"""

        print "** updateOpenNRWSchemaConnectionEnabled"
        #TODO
    
    def calculateRoute(self):
        """Calculate Route from specified source to target using default postgis dijkstra function."""

        print "** calculateRoute"
        
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
            function.prepare(self.canvasItemList)
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
                    QMessageBox.critical(self.dock, self.dockwidget.windowTitle(),
                        'server closed the connection unexpectedly')
        
    def executeTestFuntion2(self):
        """Run test function 2"""

        print "** executeTestFunction2"
        #TODO
    
    def getArguments(self, controls):
        args = {}       #'dict'
        args['edge_schema'] = str(self.dockwidget.comboBoxEdgesSchema.currentText())
        args['edge_table'] = self.dockwidget.lineEditEdgesTable.text()
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

#         if 'lineEditX1' in controls:
#             args['x1'] = self.dockwidget.lineEditX1.text()
#         
#         if 'lineEditY1' in controls:
#             args['y1'] = self.dockwidget.lineEditY1.text()
#         
#         if 'lineEditX2' in controls:
#             args['x2'] = self.dockwidget.lineEditX2.text()
#         
#         if 'lineEditY2' in controls:
#             args['y2'] = self.dockwidget.lineEditY2.text()
#         
#         if 'lineEditRule' in controls:
#             args['rule'] = self.dockwidget.lineEditRule.text()
#         
#         if 'lineEditToCost' in controls:
#             args['to_cost'] = self.dockwidget.lineEditToCost.text()
#         
#         if 'lineEditIds' in controls:
#             args['ids'] = self.dockwidget.lineEditIds.text()
# 
#         if 'lineEditPcts' in controls:
#             args['pcts'] = self.dockwidget.lineEditPcts.text()

#         if 'lineEditSourcePos' in controls:
#             args['source_pos'] = self.dockwidget.lineEditSourcePos.text()
#         
#         if 'lineEditSourceIds' in controls:
#             args['source_ids'] = self.dockwidget.lineEditSourceIds.text()

#         if 'lineEditTargetPos' in controls:
#             args['target_pos'] = self.dockwidget.lineEditTargetPos.text()
#         
#         if 'lineEditTargetIds' in controls:
#             args['target_ids'] = self.dockwidget.lineEditTargetIds.text()
#         
#         if 'lineEditDistance' in controls:
#             args['distance'] = self.dockwidget.lineEditDistance.text()
#         
#         if 'lineEditAlpha' in controls:
#             args['alpha'] = self.dockwidget.lineEditAlpha.text()
#         
#         if 'lineEditPaths' in controls:
#             args['paths'] = self.dockwidget.lineEditPaths.text()

#         if 'checkBoxHeapPaths' in controls:
#             args['heap_paths'] = str(self.dockwidget.checkBoxHeapPaths.isChecked()).lower()

#         if 'checkBoxHasReverseCost' in controls:
#             args['has_reverse_cost'] = str(self.dockwidget.checkBoxHasReverseCost.isChecked()).lower()
#             if args['has_reverse_cost'] == 'false':
#                 args['reverse_cost'] = ' '
#             else:
#                 args['reverse_cost'] = ', ' + args['reverse_cost'] + '::float8 AS reverse_cost'
#         
#         if 'plainTextEditTurnRestrictSql' in controls:
#             args['turn_restrict_sql'] = self.dockwidget.plainTextEditTurnRestrictSql.toPlainText()
    
    def setDefaultArguments(self, controls):
        """Loads default arguments and fills the widget boxes with the lables"""
        
        oldReloadMessage = self.reloadMessage
        self.reloadMessage = False
        idx = self.dockwidget.comboBoxDatabase.findText('postgres')
        if idx >= 0:
            self.dockwidget.comboBoxDatabase.setCurrentIndex(idx) #reset to previous selection
        else:
            self.dockwidget.comboBoxDatabase.setCurrentIndex(0)
        self.reloadMessage = oldReloadMessage
        
        self.dockwidget.comboBoxEdgesSchema.clear()
        self.dockwidget.comboBoxEdgesSchema.addItem('nrw_2po')
        self.dockwidget.lineEditEdgesTable.setText('nrw_2po_4pgr')
        self.dockwidget.lineEditVerticesTable.setText('nrw_2po_4pgr_vertices_pgr')
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

        layerName = "(" + letter 

        if 'directed' in args and args['directed'] == 'true':
            layerName +=  "D) "
        else:
            layerName +=  "U) "

        layerName += function.getName() + ": "


        if 'source_id' in args:
            layerName +=  args['source_id']
        elif 'ids' in args:
            layerName += "{" + args['ids'] + "}"
        else:
            layerName +=  "[" + args['source_ids'] + "]"

        if 'ids' in args:
            layerName += " "
        elif 'distance' in args:
            layerName += " dd = " + args['distance']
        else:
            layerName += " to "
            if 'target_id' in args:
                layerName += args['target_id']
            else:
                layerName += "[" + args['target_ids'] + "]"

        return layerName 
    
    def clear(self):
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
        settings = QSettings()
        idx = self.dockwidget.comboBoxDatabase.findText(Utils.getStringValue(settings, '/orientationMapsCreator/Database', ''))
        if idx >= 0:
            self.dockwidget.comboBoxDatabase.setCurrentIndex(idx)
        
        self.dockwidget.lineEditEdgesTable.setText(Utils.getStringValue(settings, '/orientationMapsCreator/sql/edge_table', 'nrw_2po_4pgr'))
        self.dockwidget.lineEditVerticesTable.setText(Utils.getStringValue(settings, '/orientationMapsCreator/sql/vertices_table', 'nrw_2po_4pgr_vertices_pgr'))
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
        settings = QSettings()
        settings.setValue('/orientationMapsCreator/Database', self.dockwidget.comboBoxDatabase.currentText())
        
        settings.setValue('/orientationMapsCreator/sql/edge_table', self.dockwidget.lineEditEdgesTable.text())
        settings.setValue('/orientationMapsCreator/sql/vertices_table', self.dockwidget.lineEditVerticesTable.text())
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

