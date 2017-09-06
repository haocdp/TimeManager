# -*- coding: utf-8 -*-
"""
Created on Fri Oct 29 10:13:39 2010

@author: agraser
"""
import os
from string import replace
import time
from PyQt4 import uic
from PyQt4 import QtGui as QtGui
from qgis._core import QgsMapLayerRegistry,QgsGraduatedSymbolRendererV2, QgsVectorLayer
from qgis.core import *

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from timevectorlayer import *
from time_util import QDateTime_to_datetime, \
    datetime_to_str, DEFAULT_FORMAT
import time_util
from bcdate_util import BCDate
import conf
import qgis_utils as qgs
from ui import label_options
import layer_settings as ls
from vectorlayerdialog import VectorLayerDialog, AddLayerDialog
from rasterlayerdialog import RasterLayerDialog
from datetime import datetime
from timemanagerprojecthandler import TimeManagerProjectHandler


# The QTSlider only supports integers as the min and max, therefore the maximum maximum value
# is whatever can be stored in an int. Making it a signed int to be sure.
# (http://qt-project.org/doc/qt-4.8/qabstractslider.html)
MAX_TIME_LENGTH_SECONDS_SLIDER = 2 ** 31 - 1
# according to the docs of QDateTime, the minimum date supported is the first day of
# year 100  (http://qt-project.org/doc/qt-4.8/qdatetimeedit.html#minimumDate-prop)
MIN_QDATE = QDate(100, 1, 1)

DOCK_WIDGET_FILE = "dockwidget2.ui"
ADD_VECTOR_LAYER_WIDGET_FILE = "addLayer.ui"
ADD_RASTER_LAYER_WIDGET_FILE = "addRasterLayer.ui"
ARCH_WIDGET_FILE = "arch.ui"
OPTIONS_WIDGET_FILE = "options.ui"
ANIMATION_WIDGET_FILE = "animate.ui"
SELECT_VECTOR_LAYER = "selectVectorLayer.ui"
GENERATE_OD = "generateOd.ui"
BROSWER_DIALOG = "webView.ui"

# TAZ分隔区间数组
TAZ_INTENSITY_THRESHOLD = [0, 80.0, 160.0, 240.0, 320.0, 400.0, 480.0, 560.0]

class TimestampLabelConfig(object):
    """Object that has the settings for rendering timestamp labels. Can be customized via the UI"""
    PLACEMENTS = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
    DEFAULT_FONT_SIZE = 4
    font = "Arial"  # Font names or family, comma-separated CSS style
    size = DEFAULT_FONT_SIZE  # Relative values between 1-7
    fmt = DEFAULT_FORMAT  # Pythonic format (same as in the layers)
    placement = 'SE'  # Choose from
    color = 'black'  # Text color as name, rgb(RR,GG,BB), or #XXXXXX
    bgcolor = 'white'  # Background color as name, rgb(RR,GG,BB), or #XXXXXX
    type ="dt"
    

    def __init__(self, model):
        self.model = model

    def getLabel(self, dt):
        if self.type=="dt":
            return datetime_to_str(dt, self.fmt)
        if self.type=="epoch":
            return "Seconds elapsed: {}".format((dt - datetime(1970,1,1,0,0)).total_seconds())
        if self.type=="beginning":
            min_dt =  self.model.getProjectTimeExtents()[0]
            return "Seconds elapsed: {}".format((dt - min_dt).total_seconds())
        else:
            raise Exception("Unsupported type {}".format(self.type))

class TimeManagerGuiControl(QObject):
    """This class controls all plugin-related GUI elements. Emitted signals are defined here."""

    setFlag = 0

    showOptions = pyqtSignal()
    autoSetOptions = pyqtSignal() # 自动设置信号
    odAnalysis = pyqtSignal()
    
    setTimeSliderSignal = pyqtSignal()
    
    signalExportVideo = pyqtSignal(str, int, bool, bool, bool)
    toggleTime = pyqtSignal()
    toggleArchaeology = pyqtSignal()
    back = pyqtSignal()
    forward = pyqtSignal()
    play = pyqtSignal()
    signalCurrentTimeUpdated = pyqtSignal(object)
    signalSliderTimeChanged = pyqtSignal(float)
    signalTimeFrameType = pyqtSignal(str)
    signalTimeFrameSize = pyqtSignal(int)
    signalSaveOptions = pyqtSignal()
    signalArchDigitsSpecified = pyqtSignal(int)
    signalArchCancelled = pyqtSignal()

    def __init__(self, iface, model):
        """initialize the GUI control"""
        QObject.__init__(self)
        self.iface = iface
        self.model = model
        self.optionsDialog = None
        self.path = os.path.dirname(os.path.abspath(__file__))

        # load the form
        self.dock = uic.loadUi(os.path.join(self.path, DOCK_WIDGET_FILE))
        self.iface.addDockWidget(Qt.BottomDockWidgetArea, self.dock)

        self.dock.pushButtonExportVideo.setEnabled(
            False)  # only enabled if there are managed layers
        self.dock.pushButtonOptions.clicked.connect(self.optionsClicked)

        # 绑定按钮与方法
        self.dock.pushButtonAutoSet.clicked.connect(self.autoSetClicked)
        
        # od分析
        self.dock.pushButtonOdAnalysis.clicked.connect(self.odAnalysisClicked)
        # 计算OD强度
        # self.dock.pushButtonAnalysis.clicked.connect(self.generateOdData)
        
        # self.dock.pushButtonSetTimeSlider.clicked.connect(self.setTimeSlider)
        self.dock.pushButtonSetTimeSlider.clicked.connect(self.showSelectVectorLayer)
        self.dock.pushButtonSetPolygonTimeSlider.clicked.connect(self.showSelectRegionLayer)
        
        self.dock.radioButton_origin.hide()
        self.dock.radioButton_destination.hide()
        
        self.dock.pushButtonBroswerDialog.clicked.connect(self.showBroswerDialog)
        
        self.dock.pushButtonExportVideo.clicked.connect(self.exportVideoClicked)
        self.dock.pushButtonToggleTime.clicked.connect(self.toggleTimeClicked)
        self.dock.pushButtonArchaeology.clicked.connect(self.archaeologyClicked)
        self.dock.pushButtonBack.clicked.connect(self.backClicked)
        self.dock.pushButtonForward.clicked.connect(self.forwardClicked)
        self.dock.pushButtonPlay.clicked.connect(self.playClicked)
        self.dock.dateTimeEditCurrentTime.dateTimeChanged.connect(self.currentTimeChangedDateText)
        
        self.dock.horizontalTimeSlider.valueChanged.connect(self.currentTimeChangedSlider)
            
        self.dock.comboBoxTimeExtent.currentIndexChanged[str].connect(
            self.currentTimeFrameTypeChanged)
        self.dock.spinBoxTimeExtent.valueChanged.connect(self.currentTimeFrameSizeChanged)

        # this signal is responsible for rendering the label
        self.iface.mapCanvas().renderComplete.connect(self.renderLabel)

        # create shortcuts
        self.focusSC = QShortcut(QKeySequence("Ctrl+Space"), self.dock)
        self.connect(self.focusSC, QtCore.SIGNAL('activated()'),
                     self.dock.horizontalTimeSlider.setFocus)

        # put default values
        self.dock.horizontalTimeSlider.setMinimum(conf.MIN_TIMESLIDER_DEFAULT)
        self.dock.horizontalTimeSlider.setMaximum(conf.MAX_TIMESLIDER_DEFAULT)
        self.dock.dateTimeEditCurrentTime.setMinimumDate(MIN_QDATE)
        self.showLabel = conf.DEFAULT_SHOW_LABEL
        self.exportEmpty = conf.DEFAULT_EXPORT_EMPTY
        self.labelOptions = TimestampLabelConfig(self.model)

        # placeholders for widgets that are added dynamically
        self.bcdateSpinBox = None

        # add to plugins toolbar
        try:
            self.action = QAction("Toggle visibility", self.iface.mainWindow())
            self.action.triggered.connect(self.toggleDock)
            self.iface.addPluginToMenu("&TimeManager", self.action)
        except:
            pass  # OK for testing
        
        self.layer = None

    def getLabelFormat(self):
        return self.labelOptions.fmt
        
    def getLabelFont(self):
        return self.labelOptions.font
        
    def getLabelSize(self):
        return self.labelOptions.size
        
    def getLabelColor(self):
        return self.labelOptions.color
        
    def getLabelBgColor(self):
        return self.labelOptions.bgcolor
        
    def getLabelPlacement(self):
        return self.labelOptions.placement

    def setLabelFormat(self, fmt):
        if not fmt:
            return
        self.labelOptions.fmt = fmt
        
    def setLabelFont(self, font):
        if not font:
            return
        self.labelOptions.font = font
        
    def setLabelSize(self, size):
        if not size:
            return
        self.labelOptions.size = size
        
    def setLabelColor(self, color):
        if not color:
            return 
        self.labelOptions.color = color
        
    def setLabelBgColor(self, bgcolor):
        if not bgcolor:
            return
        self.labelOptions.bgcolor = bgcolor
        
    def setLabelPlacement(self, placement):
        if not placement:
            return
        self.labelOptions.placement = placement

    def toggleDock(self):
        self.dock.setVisible(not self.dock.isVisible())

    def getOptionsDialog(self):
        return self.optionsDialog

    def showAnimationOptions(self):
        self.animationDialog = uic.loadUi(os.path.join(self.path, ANIMATION_WIDGET_FILE))

        def selectFile():
            self.animationDialog.lineEdit.setText(QFileDialog.getOpenFileName())

        self.animationDialog.pushButton.clicked.connect(self.selectAnimationFolder)
        self.animationDialog.buttonBox.accepted.connect(self.sendAnimationOptions)
        self.animationDialog.show()

    def selectAnimationFolder(self):

        prev_directory = TimeManagerProjectHandler.plugin_setting(conf.LAST_ANIMATION_PATH_TAG)
        if prev_directory:
            self.animationDialog.lineEdit.setText(QtGui.QFileDialog.getExistingDirectory(directory=prev_directory))
        else:
            self.animationDialog.lineEdit.setText(QtGui.QFileDialog.getExistingDirectory())

    def sendAnimationOptions(self):
        path = self.animationDialog.lineEdit.text()
        if path == "":
            self.showAnimationOptions()
        TimeManagerProjectHandler.set_plugin_setting(conf.LAST_ANIMATION_PATH_TAG, path)
        delay_millis = self.animationDialog.spinBoxDelay.value()
        export_gif = self.animationDialog.radioAnimatedGif.isChecked()
        export_video = self.animationDialog.radioVideo.isChecked()
        do_clear = self.animationDialog.clearCheckBox.isChecked()
        self.signalExportVideo.emit(path, delay_millis, export_gif, export_video, do_clear)

    def showLabelOptions(self):
        # TODO maybe more clearly
        self.dialog = QtGui.QDialog()
        self.labelOptionsDialog = label_options.Ui_labelOptions()
        self.labelOptionsDialog.setupUi(self.dialog)
        self.labelOptionsDialog.fontsize.setValue(self.labelOptions.size)
        self.labelOptionsDialog.time_format.setText(self.labelOptions.fmt)
        self.labelOptionsDialog.font.setCurrentFont(QFont(self.labelOptions.font))
        self.labelOptionsDialog.placement.addItems(TimestampLabelConfig.PLACEMENTS)
        self.labelOptionsDialog.placement.setCurrentIndex(TimestampLabelConfig.PLACEMENTS.index(
            self.labelOptions.placement))
        self.labelOptionsDialog.text_color.setColor(QColor(self.labelOptions.color))
        self.labelOptionsDialog.bg_color.setColor(QColor(self.labelOptions.bgcolor))
        self.labelOptionsDialog.buttonBox.accepted.connect(self.saveLabelOptions)

        self.dialog.show()

    def saveLabelOptions(self):
        self.labelOptions.font = self.labelOptionsDialog.font.currentFont().family()
        self.labelOptions.size = self.labelOptionsDialog.fontsize.value()
        self.labelOptions.bgcolor = self.labelOptionsDialog.bg_color.color().name()
        self.labelOptions.color = self.labelOptionsDialog.text_color.color().name()
        self.labelOptions.placement = self.labelOptionsDialog.placement.currentText()
        self.labelOptions.fmt = self.labelOptionsDialog.time_format.text()
        if self.labelOptionsDialog.radioButton_dt.isChecked():
            self.labelOptions.type = "dt"
        if self.labelOptionsDialog.radioButton_beginning.isChecked():
            self.labelOptions.type = "beginning"
        if self.labelOptionsDialog.radioButton_epoch.isChecked():
            self.labelOptions.type = "epoch"

    def enableArchaeologyTextBox(self):
        self.dock.dateTimeEditCurrentTime.dateTimeChanged.connect(self.currentTimeChangedDateText)
        if self.bcdateSpinBox is None:
            self.bcdateSpinBox = self.createBCWidget(self.dock)
            self.bcdateSpinBox.editingFinished.connect(self.currentBCYearChanged)
        self.replaceWidget(self.dock.horizontalLayout, self.dock.dateTimeEditCurrentTime,
                           self.bcdateSpinBox, 5)

    def getTimeWidget(self):
        if time_util.is_archaelogical():
            return self.bcdateSpinBox
        else:
            return self.dock.dateTimeEditCurrentTime

    def currentBCYearChanged(self):
        val = self.bcdateSpinBox.text()
        try:
            bcdate = BCDate.from_str(val, strict_zeros=False)
            self.signalCurrentTimeUpdated.emit(val)
        except:
            warn("Invalid bc date: {}".format(val))  # how to mark as such?
            return

    def disableArchaeologyTextBox(self):
        if self.bcdateSpinBox is None:
            return
        self.replaceWidget(self.dock.horizontalLayout, self.bcdateSpinBox,
                           self.dock.dateTimeEditCurrentTime, 5)

    def createBCWidget(self, mainWidget):
        newWidget = QtGui.QLineEdit(mainWidget)  # QtGui.QSpinBox(mainWidget)
        # newWidget.setMinimum(-1000000)
        #newWidget.setValue(-1)
        newWidget.setText("0001 BC")
        return newWidget

    def replaceWidget(self, layout, oldWidget, newWidget, idx):
        """Replaces oldWidget with newWidget at layout at index idx
        The way it is done, the widget is not destroyed
        and the connections to it remain"""

        layout.removeWidget(oldWidget)
        oldWidget.close()  # I wonder if this has any memory leaks? </philosoraptor>
        layout.insertWidget(idx, newWidget)
        newWidget.show()
        layout.update()

    def optionsClicked(self):
        self.showOptions.emit()

    def exportVideoClicked(self):
        self.showAnimationOptions()

    def toggleTimeClicked(self):
        self.toggleTime.emit()

    def archaeologyClicked(self):
        self.toggleArchaeology.emit()

    def showArchOptions(self):
        self.archMenu = uic.loadUi(os.path.join(self.path, ARCH_WIDGET_FILE))
        self.archMenu.buttonBox.accepted.connect(self.saveArchOptions)
        self.archMenu.buttonBox.rejected.connect(self.cancelArch)
        self.archMenu.show()

    def saveArchOptions(self):
        self.signalArchDigitsSpecified.emit(self.archMenu.numDigits.value())

    def cancelArch(self):
        self.signalArchCancelled.emit()

    def backClicked(self):
        self.back.emit()

    def forwardClicked(self):
        self.forward.emit()

    def playClicked(self):
        if self.dock.pushButtonPlay.isChecked():
            self.dock.pushButtonPlay.setIcon(QIcon(":/images/pause.png"))
        else:
            self.dock.pushButtonPlay.setIcon(QIcon(":/images/play.png"))
        self.play.emit()


    def currentTimeChangedSlider(self, sliderVal):
        try:
            pct = (sliderVal - self.dock.horizontalTimeSlider.minimum()) * 1.0 / (
                self.dock.horizontalTimeSlider.maximum() - self.dock.horizontalTimeSlider.minimum())
        except:
            # slider is not properly initialized yet
            return
        if self.model.getActiveDelimitedText() and qgs.getVersion() < conf.MIN_DTEXT_FIXED:
            time.sleep(
                0.1)  # hack to fix issue in qgis core with delimited text which was fixed in 2.9
        self.signalSliderTimeChanged.emit(pct)

    def currentTimeChangedDateText(self, qdate):
        # info("changed time via text")
        self.signalCurrentTimeUpdated.emit(qdate)

    def currentTimeFrameTypeChanged(self, frameType):
        self.signalTimeFrameType.emit(frameType)

    def currentTimeFrameSizeChanged(self, frameSize):
        if frameSize < 1:  # time frame size = 0  is meaningless
            self.dock.spinBoxTimeExtent.setValue(1)
            return
        self.signalTimeFrameSize.emit(frameSize)

    def unload(self):
        """unload the plugin"""
        self.iface.removeDockWidget(self.dock)
        self.iface.removePluginMenu("TimeManager", self.action)

    def setWindowTitle(self, title):
        self.dock.setWindowTitle(title)

    def showOptionsDialog(self, layerList, animationFrameLength, playBackwards=False,
                          loopAnimation=False):
        """show the optionsDialog and populate it with settings from timeLayerManager"""

        # load the form
        self.optionsDialog = uic.loadUi(os.path.join(self.path, OPTIONS_WIDGET_FILE))

        # restore settings from layerList:
        for layer in layerList:
            settings = ls.getSettingsFromLayer(layer)
            ls.addSettingsToRow(settings, self.optionsDialog.tableWidget)

        # restore animation options
        self.optionsDialog.spinBoxFrameLength.setValue(animationFrameLength)
        self.optionsDialog.checkBoxBackwards.setChecked(playBackwards)
        self.optionsDialog.checkBoxLabel.setChecked(self.showLabel)
        self.optionsDialog.checkBoxDontExportEmpty.setChecked(not self.exportEmpty)
        self.optionsDialog.checkBoxLoop.setChecked(loopAnimation)
        self.optionsDialog.show_label_options_button.clicked.connect(self.showLabelOptions)
        self.optionsDialog.checkBoxLabel.stateChanged.connect(self.showOrHideLabelOptions)

        # show dialog
        self.showOrHideLabelOptions()
        self.optionsDialog.show()

        # create raster and vector dialogs
        self.vectorDialog = VectorLayerDialog(self.iface, os.path.join(self.path,
                                                                       ADD_VECTOR_LAYER_WIDGET_FILE),
                                              self.optionsDialog.tableWidget)
        self.rasterDialog = RasterLayerDialog(self.iface, os.path.join(self.path,
                                                                       ADD_RASTER_LAYER_WIDGET_FILE),
                                              self.optionsDialog.tableWidget)
        # establish connections
        self.optionsDialog.pushButtonAddVector.clicked.connect(self.vectorDialog.show)
        self.optionsDialog.pushButtonAddRaster.clicked.connect(self.rasterDialog.show)
        self.optionsDialog.pushButtonRemove.clicked.connect(self.removeLayer)
        self.optionsDialog.buttonBox.accepted.connect(self.saveOptions)
        self.optionsDialog.buttonBox.helpRequested.connect(self.showHelp)

    def showOrHideLabelOptions(self):
        self.optionsDialog.show_label_options_button.setEnabled(
            self.optionsDialog.checkBoxLabel.isChecked())

    def showHelp(self):
        """show the help dialog"""
        self.helpDialog = uic.loadUi(os.path.join(self.path, "help.ui"))
        helpPath = QUrl(
            'file:///' + replace(os.path.join(self.path, "help.htm"), '\\', '/'))  # windows
        # hack: Qt expects / instead of \
        # QMessageBox.information(self.iface.mainWindow(),'Error',str(helpPath))
        self.helpDialog.textBrowser.setSource(helpPath)
        self.helpDialog.show()

    def saveOptions(self):
        """save the options from optionsDialog to timeLayerManager"""
        self.signalSaveOptions.emit()

    def removeLayer(self):
        """removes the currently selected layer (= row) from options"""
        currentRow = self.optionsDialog.tableWidget.currentRow()
        try:
            layerName = self.optionsDialog.tableWidget.item(currentRow, 0).text()
        except AttributeError:  # if no row is selected
            return
        if QMessageBox.question(self.optionsDialog, 'Remove Layer',
                                'Do you really want to remove layer ' + layerName + '?',
                                QMessageBox.Ok, QMessageBox.Cancel) == QMessageBox.Ok:
            self.optionsDialog.tableWidget.removeRow(self.optionsDialog.tableWidget.currentRow())

    def disableAnimationExport(self):
        """disable the animation export button"""
        self.dock.pushButtonExportVideo.setEnabled(False)

    def enableAnimationExport(self):
        """enable the animation export button"""
        self.dock.pushButtonExportVideo.setEnabled(True)

    def refreshMapCanvas(self, sender=None):
        """refresh the map canvas"""
        # QMessageBox.information(self.iface.mainWindow(),'Test Output','Refresh!\n'+str(sender))
        self.iface.mapCanvas().refresh()

    def setTimeFrameSize(self, frameSize):
        """set spinBoxTimeExtent to given frameSize"""
        self.dock.spinBoxTimeExtent.setValue(frameSize)

    def setTimeFrameType(self, frameType):
        """set comboBoxTimeExtent to given frameType"""
        i = self.dock.comboBoxTimeExtent.findText(frameType)
        self.dock.comboBoxTimeExtent.setCurrentIndex(i)

    def setActive(self, isActive):
        """set pushButtonToggleTime active/inactive"""
        self.dock.pushButtonToggleTime.setChecked(isActive)

    def setArchaeologyPressed(self, isActive):
        """set pushButtonArchaeology active/inactive"""
        self.dock.pushButtonArchaeology.setChecked(isActive)

    def addActionShowSettings(self, action):
        """add action to pushButttonOptions"""
        self.dock.pushButtonOptions.addAction(action)

    def turnPlayButtonOff(self):
        """turn pushButtonPlay off"""
        if self.dock.pushButtonPlay.isChecked():
            self.dock.pushButtonPlay.toggle()

    def renderLabel(self, painter):
        """render the current timestamp on the map canvas"""
        if not self.showLabel or not self.model.hasLayers() or not self.dock.pushButtonToggleTime.isChecked():
            return

        dt = self.model.getCurrentTimePosition()
        if dt is None:
            return

        labelString = self.labelOptions.getLabel(dt)

        # Determine placement of label given cardinal directions
        flags = 0
        for direction, flag in ('N', Qt.AlignTop), ('S', Qt.AlignBottom),\
                ('E', Qt.AlignRight), ('W', Qt.AlignLeft):
            if direction in self.labelOptions.placement:
                flags |= flag

        # Get canvas dimensions
        width = painter.device().width()
        height = painter.device().height()

        painter.setRenderHint(painter.Antialiasing, True)
        txt = QTextDocument()
        html = '<span style="background-color:%s; padding: 5px;"><font face="%s" size="%s" color="%s">%s</font></span>'\
            % (self.labelOptions.bgcolor, self.labelOptions.font, self.labelOptions.size,
                self.labelOptions.color, labelString)
        txt.setHtml(html)
        layout = txt.documentLayout()
        size = layout.documentSize()

        if flags & Qt.AlignRight:
            x = width - 5 - size.width()
        elif flags & Qt.AlignLeft:
            x = 5
        else:
            x = width / 2 - size.width() / 2

        if flags & Qt.AlignBottom:
            y = height - 5 - size.height()
        elif flags & Qt.AlignTop:
            y = 5
        else:
            y = height / 2 - size.height() / 2

        painter.translate(x, y)
        layout.draw(painter, QAbstractTextDocumentLayout.PaintContext())
        painter.translate(-x, -y)  # translate back

    def repaintRasters(self):
        rasters = self.model.getActiveRasters()
        map(lambda x: x.layer.triggerRepaint(), rasters)

    def repaintVectors(self):
        map(lambda x: x.layer.triggerRepaint(), self.model.getActiveVectors())

    def repaintJoined(self):
        layerIdsToRefresh = qgs.getAllJoinedLayers(
            set(map(lambda x: x.layer.id(), self.model.getActiveVectors())))
        # info("to refresh {}".format(layerIdsToRefresh))
        layersToRefresh = map(lambda x: qgs.getLayerFromId(x), layerIdsToRefresh)
        map(lambda x: x.triggerRepaint(), layersToRefresh)





    # 点击“自动设置”按钮调用该方法
    def autoSetClicked(self):
        self.autoSetOptions.emit()


    def autoSet(self, layerList, animationFrameLength, playBackwards=False,
                          loopAnimation=False):
        # load the form
        self.optionsDialog = uic.loadUi(os.path.join(self.path, OPTIONS_WIDGET_FILE))

        # restore settings from layerList:
        for layer in layerList:
            settings = ls.getSettingsFromLayer(layer)
            ls.addSettingsToRow(settings, self.optionsDialog.tableWidget)

        # restore animation options
        self.optionsDialog.spinBoxFrameLength.setValue(animationFrameLength)
        self.optionsDialog.checkBoxBackwards.setChecked(playBackwards)
        self.optionsDialog.checkBoxLabel.setChecked(self.showLabel)
        self.optionsDialog.checkBoxDontExportEmpty.setChecked(not self.exportEmpty)
        self.optionsDialog.checkBoxLoop.setChecked(loopAnimation)
        self.optionsDialog.show_label_options_button.clicked.connect(self.showLabelOptions)
        self.optionsDialog.checkBoxLabel.stateChanged.connect(self.showOrHideLabelOptions)

        # create raster and vector dialogs
        self.vectorDialog = VectorLayerDialog(self.iface, os.path.join(self.path,
                                                                       ADD_VECTOR_LAYER_WIDGET_FILE),
                                              self.optionsDialog.tableWidget)

        self.vectorDialog.set()
        self.signalSaveOptions.emit()


    def odAnalysisClicked(self):
        self.odAnalysis.emit()
        
    # 显示选择图层的窗口
    def showSelectVectorLayer(self):
        if self.setFlag == 0:
            self.selectLayerDialog = uic.loadUi(os.path.join(self.path, SELECT_VECTOR_LAYER))
            layers = self.iface.legendInterface().layers()
            layer_list = []
            for layer in layers:
                layer_list.append(layer.name())
            self.selectLayerDialog.comboBox.addItems(layer_list)
            
            # 隐藏单选框
            # self.selectLayerDialog.label_2.hide()
            
            self.selectLayerDialog.show()
        
            result = self.selectLayerDialog.exec_()
            if result:
                # self.selectLayerDialog.buttonBox.accepted.connect(setTimeSlider)
                selectedLayerIndex = self.selectLayerDialog.comboBox.currentIndex()
                self.layer = layers[selectedLayerIndex]
                if not isinstance(self.layer, QgsVectorLayer) :
                    QMessageBox.information(self.iface.mainWindow(), 'Info',
                                    u'图层不是矢量图层')
                elif self.layer.featureCount() == 0:
                    QMessageBox.information(self.iface.mainWindow(), 'Info',
                                    u'图层元素为空')
                elif not self.layer.geometryType() == QGis.Line :
                    QMessageBox.information(self.iface.mainWindow(), 'Info',
                                    u'图层不是直线图层')
                else :
                    self.setTimeSlider()
        else:
            self.setTimeSlider()
    
    # 设置时间序列为24个小时按每小时刷新
    def setTimeSlider(self):
        
        if self.setFlag == 0:
            self.setFlag = 1
            self.dock.pushButtonOptions.setDisabled(True)
            self.dock.dateTimeEditCurrentTime.setDisabled(True)
            self.dock.pushButtonOdAnalysis.setDisabled(True)
            self.dock.pushButtonBack.setDisabled(True)
            self.dock.pushButtonForward.setDisabled(True)
            self.dock.spinBoxTimeExtent.setValue(1)
            self.setTimeFrameType(u'小时')
            
            self.dock.spinBoxTimeExtent.setDisabled(True)
            self.dock.comboBoxTimeExtent.setDisabled(True)
            self.dock.pushButtonSetPolygonTimeSlider.setDisabled(True)
            self.setTimeSliderSignal.emit()
            # 当设置为时序控制时绑定不同的触发方法
            self.dock.horizontalTimeSlider.valueChanged.connect(self.timeSliderChanged)
            self.dock.pushButtonPlay.clicked.connect(self.autoPlay)
            
            self.dock.pushButtonSetTimeSlider.setText(u"取消设置")
            
            self.signalTimeFrameType.emit(u'小时')
            
            # self.initTimeSlider()
        else :
            self.setFlag = 0
            self.dock.pushButtonOptions.setDisabled(False)
            self.dock.dateTimeEditCurrentTime.setDisabled(False)
            self.dock.pushButtonOdAnalysis.setDisabled(False)
            self.dock.pushButtonBack.setDisabled(False)
            self.dock.pushButtonForward.setDisabled(False)
            self.dock.spinBoxTimeExtent.setDisabled(False)
            self.dock.comboBoxTimeExtent.setDisabled(False)
            self.dock.pushButtonSetPolygonTimeSlider.setDisabled(False)
            
            self.dock.pushButtonSetTimeSlider.setText(u"设置连接线时序")
            
            # self.qTimer = None
            # self.layer = None
            self.dock.horizontalTimeSlider.valueChanged.connect(self.currentTimeChangedSlider)
            self.dock.pushButtonPlay.clicked.connect(self.playClicked)
            
    def initTimeSlider(self):
        # layers = QgsMapLayerRegistry.instance().mapLayers()
        # items = layers.items()
        # keys = [x[0] for x in layers.items() if 'line2' in x[1]]
        # self.layer = layers.get(keys[0])
        # self.layer = layers.get('line220170821165451339')
        
        min = 1
        max = 24
        step = 1
        self.dock.labelStartTime.setText(str(min))
        self.dock.labelEndTime.setText(str(max))
        self.dock.horizontalTimeSlider.setMinimum(min)
        self.dock.horizontalTimeSlider.setMaximum(max)
        self.dock.horizontalTimeSlider.setSingleStep(step)
        #self.dock.horizontalTimeSlider.valueChanged.connect(self.timeSliderChanged)
        
        # 定时器
        self.qTimer = QTimer(self)
        self.qTimer.timeout.connect(self.incrementValue)
        
        # 渲染样式
        myRangeList = []
        
        # symbol 1
        myMin = 0.0
        myMax = 2000.0
        myLabel = '0.0 - 2000.0'
        myColour = QtGui.QColor('#fff5eb')
        mySymbol1 = QgsSymbolV2.defaultSymbol(self.layer.geometryType())
        mySymbol1.setColor(myColour)
        mySymbol1.setAlpha(0)
        mySymbol1.setWidth(0)
        myRange1 = QgsRendererRangeV2(myMin, myMax, mySymbol1, myLabel)
        myRangeList.append(myRange1)
        
        # symbol 2
        myMin = 2000.0
        myMax = 4000.0
        myLabel = '2000.0 - 4000.0'
        myColour = QtGui.QColor('#fdd1a5')
        mySymbol2 = QgsSymbolV2.defaultSymbol(self.layer.geometryType())
        mySymbol2.setColor(myColour)
        mySymbol2.setAlpha(0.2)
        mySymbol2.setWidth(0.5)
        myRange2 = QgsRendererRangeV2(myMin, myMax, mySymbol2, myLabel)
        myRangeList.append(myRange2)
        
        # symbol 3
        myMin = 4000.0
        myMax = 6000.0
        myLabel = '4000.0 - 6000.0'
        myColour = QtGui.QColor('#fd9243')
        mySymbol3 = QgsSymbolV2.defaultSymbol(self.layer.geometryType())
        mySymbol3.setColor(myColour)
        mySymbol3.setAlpha(0.4)
        mySymbol3.setWidth(0.8)
        myRange3 = QgsRendererRangeV2(myMin, myMax, mySymbol3, myLabel)
        myRangeList.append(myRange3)
        
        # symbol 4
        myMin = 6000.0
        myMax = 8000.0
        myLabel = '6000.0 - 8000.0'
        myColour = QtGui.QColor('#de4f05')
        mySymbol4 = QgsSymbolV2.defaultSymbol(self.layer.geometryType())
        mySymbol4.setColor(myColour)
        mySymbol4.setAlpha(0.6)
        mySymbol4.setWidth(1)
        myRange4 = QgsRendererRangeV2(myMin, myMax, mySymbol4, myLabel)
        myRangeList.append(myRange4)
        
        # symbol 5
        myMin = 8000.0
        myMax = 10000.0
        myLabel = '8000.0 - 10000.0'
        myColour = QtGui.QColor('#7f2704')
        mySymbol5 = QgsSymbolV2.defaultSymbol(self.layer.geometryType())
        mySymbol5.setColor(myColour)
        mySymbol5.setAlpha(1)
        mySymbol5.setWidth(1.3)
        myRange5 = QgsRendererRangeV2(myMin, myMax, mySymbol5, myLabel)
        myRangeList.append(myRange5)
        
        self.myRenderer = QgsGraduatedSymbolRendererV2('', myRangeList)
        self.myRenderer.setMode(QgsGraduatedSymbolRendererV2.EqualInterval)
        
    # 时序值改变时触发的方法：修改图层渲染属性
    def timeSliderChanged(self, value=None):
        if value == None:
            value = self.dock.horizontalTimeSlider.value() 
            
        if value <= 24:
            self.myRenderer.setClassAttribute(str(value))
            self.layer.setRendererV2(self.myRenderer)
            
            # renderer = self.layer.rendererV2()
            # renderer.setClassAttribute(str(value))
            # self.layer.setRendererV2(renderer)
            
            if hasattr(self.layer, "setCacheImage"):
                self.layer.setCacheImage(None)
            
            self.layer.triggerRepaint()
            self.iface.legendInterface().refreshLayerSymbology(self.layer)
        else:
            self.qTimer.stop()
            self.dock.horizontalTimeSlider.setValue(1)
        
    # 自动播放按钮
    def autoPlay(self):
        if self.dock.pushButtonPlay.isChecked():
            self.dock.pushButtonPlay.setIcon(QIcon(":/images/pause.png"))
            time = 1000
            self.qTimer.start(time)
        else:
            self.dock.pushButtonPlay.setIcon(QIcon(":/images/play.png"))
            self.qTimer.stop()
            
        
    def incrementValue(self):
        value = self.dock.horizontalTimeSlider.value()
        if value == 24:
            self.qTimer.stop()
            self.dock.horizontalTimeSlider.setValue(1)
            self.dock.pushButtonPlay.setChecked(False)
            self.dock.pushButtonPlay.setIcon(QIcon(":/images/play.png"))
            return
        self.dock.horizontalTimeSlider.setValue(value + 1)
        
    # "生成od数据"按钮点击触发
    def generateOdData(self):
        self.generateOdDialog = uic.loadUi(os.path.join(self.path, GENERATE_OD))
        layers = self.iface.legendInterface().layers()
        layer_list = []
        for layer in layers:
            layer_list.append(layer.name())
        self.generateOdDialog.comboBox.addItems(layer_list)
        self.generateOdDialog.comboBox_2.addItems(layer_list)
        self.generateOdDialog.comboBox_3.addItems(layer_list)
        self.generateOdDialog.show()
        
        self.generateOdDialog.pushButton.clicked.connect(self.generateOdDialog_accepted)
        
    
    def generateOdDialog_accepted(self):
        regionLayerIndex = self.generateOdDialog.comboBox.currentIndex()
        lineLayerIndex = self.generateOdDialog.comboBox_2.currentIndex()
        pointLayerIndex = self.generateOdDialog.comboBox_3.currentIndex()
        
        layers = self.iface.legendInterface().layers()
        self.regionLayer = layers[regionLayerIndex]
        self.lineLayer = layers[lineLayerIndex]
        self.pointLayer = layers[pointLayerIndex]
        
        if not isinstance(self.regionLayer, QgsVectorLayer) :
            QMessageBox.information(self.iface.mainWindow(), 'Info',
                            u'区域图层不是矢量图层')
        elif self.regionLayer.featureCount() == 0:
            QMessageBox.information(self.iface.mainWindow(), 'Info',
                            u'区域图层元素为空')
        elif not self.regionLayer.geometryType() == QGis.Polygon :
            QMessageBox.information(self.iface.mainWindow(), 'Info',
                            u'区域图层不是多边形图层')
        
        elif not isinstance(self.lineLayer, QgsVectorLayer) :
            QMessageBox.information(self.iface.mainWindow(), 'Info',
                            u'直线图层不是矢量图层')
        elif self.lineLayer.featureCount() == 0:
            QMessageBox.information(self.iface.mainWindow(), 'Info',
                            u'直线图层元素为空')
        elif not self.lineLayer.geometryType() == QGis.Line :
            QMessageBox.information(self.iface.mainWindow(), 'Info',
                            u'直线图层不是直线图层')
            
        elif not isinstance(self.pointLayer, QgsVectorLayer) :
            QMessageBox.information(self.iface.mainWindow(), 'Info',
                            u'轨迹点图层不是矢量图层')
        elif self.pointLayer.featureCount() == 0:
            QMessageBox.information(self.iface.mainWindow(), 'Info',
                            u'轨迹点图层元素为空')
        elif not self.pointLayer.geometryType() == QGis.Point :
            QMessageBox.information(self.iface.mainWindow(), 'Info',
                            u'轨迹点图层不是点图层')
        else :
            self.calculateOd()
    
    def calculateOd(self):
        pointFeatures = self.pointLayer.getFeatures()
        polygonFeatures = self.regionLayer.getFeatures()
        lineFeatures = self.lineLayer.getFeatures()
        
        count = 0
        totalNum = self.pointLayer.featureCount()
        
        self.generateOdDialog.progressBar.setRange(0, totalNum)
        
        for pointFeature in pointFeatures:
            origin_longitude = pointFeature['origin_longitude']
            origin_latitude = pointFeature['origin_latitude']
            destination_longitude = pointFeature['destination_longitude']
            destination_latitude = pointFeature['destination_latitude']
            destination_time = pointFeature['destination_time']
            
            for polygonFeature in polygonFeatures:
                if polygonFeature.geometry().contains(QgsPoint(origin_longitude, origin_latitude)):
                    originRegionId = polygonFeature.id()
        pass
    
    
    def showSelectRegionLayer(self):
        if self.setFlag == 0:
            self.selectLayerDialog = uic.loadUi(os.path.join(self.path, SELECT_VECTOR_LAYER))
            layers = self.iface.legendInterface().layers()
            layer_list = []
            for layer in layers:
                layer_list.append(layer.name())
            self.selectLayerDialog.comboBox.addItems(layer_list)
            self.selectLayerDialog.show()
            
            
        
            result = self.selectLayerDialog.exec_()
            if result:
                # self.selectLayerDialog.buttonBox.accepted.connect(setTimeSlider)
                selectedLayerIndex = self.selectLayerDialog.comboBox.currentIndex()
                self.regionLayer = layers[selectedLayerIndex]
                if not isinstance(self.regionLayer, QgsVectorLayer) :
                    QMessageBox.information(self.iface.mainWindow(), 'Info',
                                    u'图层不是矢量图层')
                elif self.regionLayer.featureCount() == 0:
                    QMessageBox.information(self.iface.mainWindow(), 'Info',
                                    u'图层元素为空')
                elif not self.regionLayer.geometryType() == QGis.Polygon :
                    QMessageBox.information(self.iface.mainWindow(), 'Info',
                                    u'图层不是区域图层')
                else :
                    
                    self.dock.radioButton_destination.toggled.connect(self.initRender)
                    self.dock.radioButton_origin.toggled.connect(self.initRender)
                    self.setPolygonTimeSlider()
                    
        else:
            self.setPolygonTimeSlider()
            
    def setPolygonTimeSlider(self):
        if self.setFlag == 0:
            self.setFlag = 1
            self.dock.pushButtonOptions.setDisabled(True)
            self.dock.dateTimeEditCurrentTime.setDisabled(True)
            self.dock.pushButtonOdAnalysis.setDisabled(True)
            self.dock.pushButtonBack.setDisabled(True)
            self.dock.pushButtonForward.setDisabled(True)
            self.dock.spinBoxTimeExtent.setValue(1)
            self.setTimeFrameType(u'小时')
            
            self.dock.spinBoxTimeExtent.setDisabled(True)
            self.dock.comboBoxTimeExtent.setDisabled(True)
            self.dock.pushButtonSetTimeSlider.setDisabled(True)
            self.initPolygonTimeSlider()
            
            self.dock.radioButton_destination.show()
            self.dock.radioButton_origin.show()
            
            # 当设置为时序控制时绑定不同的触发方法
            self.dock.horizontalTimeSlider.valueChanged.connect(self.polygonTimeSliderChanged)
            self.dock.pushButtonPlay.clicked.connect(self.autoPlay)
            
            self.dock.pushButtonSetPolygonTimeSlider.setText(u"取消设置")
            
            self.signalTimeFrameType.emit(u'小时')
            
            
        else :
            self.setFlag = 0
            self.dock.pushButtonOptions.setDisabled(False)
            self.dock.dateTimeEditCurrentTime.setDisabled(False)
            self.dock.pushButtonOdAnalysis.setDisabled(False)
            self.dock.pushButtonBack.setDisabled(False)
            self.dock.pushButtonForward.setDisabled(False)
            self.dock.spinBoxTimeExtent.setDisabled(False)
            self.dock.comboBoxTimeExtent.setDisabled(False)
            self.dock.pushButtonSetTimeSlider.setDisabled(False)
            
            self.dock.radioButton_destination.hide()
            self.dock.radioButton_origin.hide()
            
            self.dock.pushButtonSetPolygonTimeSlider.setText(u"设置区域时序")
            
            # self.qTimer = None
            # self.layer = None
            self.dock.horizontalTimeSlider.valueChanged.connect(self.currentTimeChangedSlider)
            self.dock.pushButtonPlay.clicked.connect(self.playClicked)
            
            
    def initRender(self):
        # 渲染样式
        myRangeList = []
        
        # symbol 1
        myMin = TAZ_INTENSITY_THRESHOLD[0]
        myMax = TAZ_INTENSITY_THRESHOLD[1]
        myLabel = str(TAZ_INTENSITY_THRESHOLD[0]) + ' - ' + str(TAZ_INTENSITY_THRESHOLD[1])
        if self.dock.radioButton_origin.isChecked():
            #myColour = QtGui.QColor('#deebf7')
            myColour = QtGui.QColor('#ffffff')
        else:
            myColour = QtGui.QColor('#ffffff')
        mySymbol1 = QgsSymbolV2.defaultSymbol(self.regionLayer.geometryType())
        mySymbol1.setColor(myColour)
        mySymbol1.setAlpha(1)
        # mySymbol1.setWidth(0)
        myRange1 = QgsRendererRangeV2(myMin, myMax, mySymbol1, myLabel)
        myRangeList.append(myRange1)
        
        # symbol 2
        myMin = TAZ_INTENSITY_THRESHOLD[1]
        myMax = TAZ_INTENSITY_THRESHOLD[2]
        myLabel = str(TAZ_INTENSITY_THRESHOLD[1]) + ' - ' + str(TAZ_INTENSITY_THRESHOLD[2])
        if self.dock.radioButton_origin.isChecked():
            myColour = QtGui.QColor('#c6dbef')
        else:
            myColour = QtGui.QColor('#c7e9c0')
        mySymbol2 = QgsSymbolV2.defaultSymbol(self.regionLayer.geometryType())
        mySymbol2.setColor(myColour)
        mySymbol2.setAlpha(1)
        # mySymbol2.setWidth(0.5)
        myRange2 = QgsRendererRangeV2(myMin, myMax, mySymbol2, myLabel)
        myRangeList.append(myRange2)
        
        # symbol 3
        myMin = TAZ_INTENSITY_THRESHOLD[2]
        myMax = TAZ_INTENSITY_THRESHOLD[3]
        myLabel = str(TAZ_INTENSITY_THRESHOLD[2]) + ' - ' + str(TAZ_INTENSITY_THRESHOLD[3])
        if self.dock.radioButton_origin.isChecked():
            myColour = QtGui.QColor('#9ecae1')
        else:
            myColour = QtGui.QColor('#a1d99b')
        mySymbol3 = QgsSymbolV2.defaultSymbol(self.regionLayer.geometryType())
        mySymbol3.setColor(myColour)
        mySymbol3.setAlpha(1)
        # mySymbol3.setWidth(0.8)
        myRange3 = QgsRendererRangeV2(myMin, myMax, mySymbol3, myLabel)
        myRangeList.append(myRange3)
        
        # symbol 4
        myMin = TAZ_INTENSITY_THRESHOLD[3]
        myMax = TAZ_INTENSITY_THRESHOLD[4]
        myLabel = str(TAZ_INTENSITY_THRESHOLD[3]) + ' - ' + str(TAZ_INTENSITY_THRESHOLD[4])
        if self.dock.radioButton_origin.isChecked():
            myColour = QtGui.QColor('#6baed6')
        else:
            myColour = QtGui.QColor('#74c476')
        mySymbol4 = QgsSymbolV2.defaultSymbol(self.regionLayer.geometryType())
        mySymbol4.setColor(myColour)
        mySymbol4.setAlpha(1)
        # mySymbol4.setWidth(1)
        myRange4 = QgsRendererRangeV2(myMin, myMax, mySymbol4, myLabel)
        myRangeList.append(myRange4)
        
        # symbol 5
        myMin = TAZ_INTENSITY_THRESHOLD[4]
        myMax = TAZ_INTENSITY_THRESHOLD[5]
        myLabel = str(TAZ_INTENSITY_THRESHOLD[4]) + ' - ' + str(TAZ_INTENSITY_THRESHOLD[5])
        if self.dock.radioButton_origin.isChecked():
            myColour = QtGui.QColor('#4292c6')
        else:
            myColour = QtGui.QColor('#41ab5d')
        mySymbol5 = QgsSymbolV2.defaultSymbol(self.regionLayer.geometryType())
        mySymbol5.setColor(myColour)
        mySymbol5.setAlpha(1)
        # mySymbol5.setWidth(1.3)
        myRange5 = QgsRendererRangeV2(myMin, myMax, mySymbol5, myLabel)
        myRangeList.append(myRange5)
        
        # symbol 6
        myMin = TAZ_INTENSITY_THRESHOLD[5]
        myMax = TAZ_INTENSITY_THRESHOLD[6]
        myLabel = str(TAZ_INTENSITY_THRESHOLD[5]) + ' - ' + str(TAZ_INTENSITY_THRESHOLD[6])
        if self.dock.radioButton_origin.isChecked():
            myColour = QtGui.QColor('#2171b5')
        else:
            myColour = QtGui.QColor('#238b45')
        mySymbol6 = QgsSymbolV2.defaultSymbol(self.regionLayer.geometryType())
        mySymbol6.setColor(myColour)
        mySymbol6.setAlpha(1)
        # mySymbol5.setWidth(1.3)
        myRange6 = QgsRendererRangeV2(myMin, myMax, mySymbol6, myLabel)
        myRangeList.append(myRange6)
        
        # symbol 7
        myMin = TAZ_INTENSITY_THRESHOLD[6]
        myMax = TAZ_INTENSITY_THRESHOLD[7]
        myLabel = str(TAZ_INTENSITY_THRESHOLD[6]) + ' - ' + str(TAZ_INTENSITY_THRESHOLD[7])
        if self.dock.radioButton_origin.isChecked():
            myColour = QtGui.QColor('#08519c')
        else:
            myColour = QtGui.QColor('#006d2c')
        mySymbol7 = QgsSymbolV2.defaultSymbol(self.regionLayer.geometryType())
        mySymbol7.setColor(myColour)
        mySymbol7.setAlpha(1)
        # mySymbol7.setWidth(1.3)
        myRange7 = QgsRendererRangeV2(myMin, myMax, mySymbol7, myLabel)
        myRangeList.append(myRange7)
        
        self.myPolygonRenderer = QgsGraduatedSymbolRendererV2('', myRangeList)
        self.myPolygonRenderer.setMode(QgsGraduatedSymbolRendererV2.EqualInterval)
        
    def initPolygonTimeSlider(self):
        min = 1
        max = 24
        step = 1
        self.dock.labelStartTime.setText(str(min))
        self.dock.labelEndTime.setText(str(max))
        self.dock.horizontalTimeSlider.setMinimum(min)
        self.dock.horizontalTimeSlider.setMaximum(max)
        self.dock.horizontalTimeSlider.setSingleStep(step)
        #self.dock.horizontalTimeSlider.valueChanged.connect(self.timeSliderChanged)
        
        # 定时器
        self.qTimer = QTimer(self)
        self.qTimer.timeout.connect(self.incrementValue)
        
        self.initRender()
    
    def polygonTimeSliderChanged(self, value = None):
        if value == None:
            value = self.dock.horizontalTimeSlider.value() 
            
        if value <= 24:
            if self.dock.radioButton_origin.isChecked():
                self.myPolygonRenderer.setClassAttribute("o" + str(value))
            else:
                self.myPolygonRenderer.setClassAttribute("d" + str(value))
            self.regionLayer.setRendererV2(self.myPolygonRenderer)
            
            # renderer = self.layer.rendererV2()
            # renderer.setClassAttribute(str(value))
            # self.layer.setRendererV2(renderer)
            
            if hasattr(self.regionLayer, "setCacheImage"):
                self.regionLayer.setCacheImage(None)
            
            self.regionLayer.triggerRepaint()
            self.iface.legendInterface().refreshLayerSymbology(self.regionLayer)
        else:
            self.qTimer.stop()
            self.dock.horizontalTimeSlider.setValue(1)
        pass
    
    
    def showBroswerDialog(self):
        self.broswerDialog = uic.loadUi(os.path.join(self.path, BROSWER_DIALOG))
        self.broswerDialog.show()
        self.broswerDialog.webView.load(QUrl("file:///C:/Users/jj/Desktop/pyqt_broswer/svg.html"))
        self.broswerDialog.webView.show()
        