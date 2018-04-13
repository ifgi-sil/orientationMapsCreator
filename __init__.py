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
 This script initializes the plugin, making it known to QGIS.
"""


# noinspection PyPep8Naming
def classFactory(iface):  # pylint: disable=invalid-name
    """Load orientationMapsCreator class from file orientationMapsCreator.

    :param iface: A QGIS interface instance.
    :type iface: QgisInterface
    """
    #
    from .orientationMapsCreator import orientationMapsCreator
    return orientationMapsCreator(iface)
