# -*- coding: UTF-8 -*-

from qgis.core import *
import qgis.utils

class ODAnalysis(object):
    
    """
        regionLayer: 区域划分图层
        odLayer: 轨迹od数据图层
    """
    def __init__(self, iface, regionLayer, odLayer, emptyLayer):
        self.iface = iface
        self.regionLayer = regionLayer
        self.odLayer = odLayer
        self.emptyLayer = emptyLayer
        self.centroids = {}
        
    """计算区域的质心，使用dict进行保存"""
    def calculateCentroid(self):
        iter = self.regionLayer.getFeatures()
        
        for feature in iter:
            geom = feature.geometry()
            # print "Feature ID %d:" % feature.id()
    
            if geom.type() == QGis.Polygon:
                # polygon = geom.asPolygon()
        
                # sum_x = 0
                # sum_y = 0
                # count = 0
                # pgeom = geom
                # for point in polygon[0]:
                #    sum_x += point.x()
                #    sum_y += point.y()
                #    count += 1
        
                # centroid = QgsPoint(sum_x/count, sum_y/count)
                self.centroids[feature.id()] = geom.centroid().asPoint()
    
    """
        todo:如何根据两个featureId快速得找到直线，需要一种数据结构存储polyline feature
                            明天的工作：
                            研究如何取出feature中的属性值
    """
    """根据区域画出两两之间的连线"""
    def drawConnectLine(self):
        caps = self.emptyLayer.dataProvider().capabilities()
        iter = self.regionLayer.getFeatures()
        
        ids = self.regionLayer.allFeatureIds()
        count = len(ids)
        totalCount = 0
        features = []
        
        
        featureId1 = 0
        while featureId1 <= count - 1:
            featureId2 = featureId1 + 1
            gPoint1 = self.centroids[ids[featureId1]]
            while featureId2 <= count - 1:
                
                gPoint2 = self.centroids[ids[featureId2]]
                gLine = QgsGeometry.fromPolyline([gPoint1, gPoint2])
                    
                if caps & QgsVectorDataProvider.AddFeatures:
                    feat = QgsFeature(self.regionLayer.pendingFields())
                    # feat.setAttribute('id', totalCount)
                    # feat.setAttribute('pointId1', ids[featureId1])
                    # feat.setAttribute('pointId2', ids[featureId2])
                    feat.setAttributes([totalCount,ids[featureId1],ids[featureId2],0])
                    feat.setGeometry(gLine)
                    features.append(feat)
                    
                    #if self.iface.mapCanvas().isCachingEnabled():
                    #    self.regionLayer.setCacheImage(None)
                    #else:
                    #    self.iface.mapCanvas().refresh()
                featureId2 += 1
                totalCount += 1
            featureId1 += 1
        [res, outFeats] = self.emptyLayer.dataProvider().addFeatures(features)
        if not res:
            QMessageBox.information(self.iface.mainWindow(), 'Error',
                                        "添加要素失败")
        self.iface.mapCanvas().refresh()
        # featureId1
        # featureId2
                        
                        
    def todo(self):
        """ 根据id找到feature """   
        request = QgsFeatureRequest().setFilterFid(1001)
        for feature in layer.getFeatures(request):
            attributes = feature.attributes() 
        layers = QgsMapLayerRegistry.instance().mapLayers()
        taz = layers.get('TAZ_1112_WGS20170816150438481')
        p = QgsPoint(113.954168563859,22.5773975032623)
        # ge = ogr.CreateGeometryFromWkt("POINT (113.954168563859 22.5773975032623)")


   
    