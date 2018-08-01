# -*- coding: utf-8 -*-
"""
Test Class to outsource calculation of the route.

TODO: would need to get access to a lot of functions and parameters of the orientationMapsCreator.
Don't yet know how to solve it.
"""

# from PyQt4.QtCore import *
# from PyQt4.QtGui import *
# from qgis.core import *
# from qgis.gui import *

class routeCalculator:
        
    def __init__(self):
        """Constructor.
        
        """
        
        print "** init routeCalculator"
        
    
    def saveRoute(self):
        """Calculate Route from specified source to target using default postgis dijkstra function.
        
        Saves Route to layer.
        """
        
        print "** saveRoute from routeCalculator"