# -*- coding: utf-8 -*-
"""
Created on Fri Oct 29 10:13:39 2010

@author: agraser
@change: cheng hao
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
import csv

from DateTransform import DateTransform

# python 调用c语言所需库
import ctypes
from ctypes import *
from __builtin__ import file


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
SELECT_DIRECTORY_DIALOG = "select_directory.ui"

# 冯博数据处理所用视图
INPUT_PARAMETER_MC_DIALOG = "inputParameter_mc.ui"
SHOW_RESULT_DOCKWIDGET = "showResult_mc.ui"

# TAZ分隔区间数组
TAZ_INTENSITY_THRESHOLD = [0, 20.0, 160.0, 240.0, 320.0, 400.0, 480.0, 560.0]
TAZ_INTENSITY_COLOR_O = ['#ffffff','#c6dbef','#9ecae1','#6baed6','#4292c6','#2171b5','#08519c']
TAZ_INTENSITY_COLOR_D = ['#ffffff','#c7e9c0','#a1d99b','#74c476','#41ab5d','#238b45','#006d2c']
LINE_INTENSITY_THRESHOLD = [0, 3, 20.0, 30.0, 40.0, 100.0]
#LINE_INTENSITY_COLOR = ['#deebf7','#9ecae1','#4292c6','#2171b5','#08519c']
#LINE_INTENSITY_COLOR = ['#fef0d9','#fdcc8a','#fc8d59','#e34a33','#b30000']
LINE_INTENSITY_COLOR = ['#ffff00','#ffb100','#ff6800','#ff3e12','#ff1320']

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
        self.dock.pushButtonSetTrajectorySlider.clicked.connect(self.showSelectDirectoryDialog)
        self.dock.pushButtonMarineOD.clicked.connect(self.showSelectDirectoryDialog_marine)
        self.dock.pushButtonPhone.clicked.connect(self.showSelectDirectoryDialog_phone)
        self.dock.comboBoxSelectMode.currentIndexChanged[str].connect(
            self.currentModeChanged)
        
        self.dock.radioButton_origin.hide()
        self.dock.radioButton_destination.hide()
        self.dock.pushButtonMarineOD.hide()
        self.dock.pushButtonPhone.hide()
        
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
        
        
        # 冯博数据分析程序
        self.dock.pushButton_mc.clicked.connect(self.showInputParameterDialog)
        
        

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
                    self.filterFeature()
                    self.setTimeSlider()
        else:
            self.filterFeature()
            self.setTimeSlider()
    
    # 对feature进行过滤
    def filterFeature(self):
        sum = 0
        featureIds = []
        if not self.layer is None:
            features = self.layer.getFeatures()
            for feature in features:
                sum = 0
                for i in range(1, 25):
                    sum = sum + feature['h' + str(i)]
                            
                if sum == 0:
                    featureIds.append(feature.id())
                            
            self.layer.dataProvider().deleteFeatures(featureIds)
    
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
        
        # symbol 5
        myMin = LINE_INTENSITY_THRESHOLD[4]
        myMax = LINE_INTENSITY_THRESHOLD[5]
        myLabel = str(LINE_INTENSITY_THRESHOLD[4]) + ' - ' + str(LINE_INTENSITY_THRESHOLD[5])
        # myColour = QtGui.QColor('#7f2704')
        myColour = QtGui.QColor(LINE_INTENSITY_COLOR[4])
        mySymbol5 = QgsSymbolV2.defaultSymbol(self.layer.geometryType())
        mySymbol5.symbolLayer(0).setRenderingPass(5)
        mySymbol5.setColor(myColour)
        mySymbol5.setAlpha(1)
        mySymbol5.setWidth(1.3)
        myRange5 = QgsRendererRangeV2(myMin, myMax, mySymbol5, myLabel)
        myRangeList.append(myRange5)
        
        # symbol 4
        myMin = LINE_INTENSITY_THRESHOLD[3]
        myMax = LINE_INTENSITY_THRESHOLD[4]
        myLabel = str(LINE_INTENSITY_THRESHOLD[3]) + ' - ' + str(LINE_INTENSITY_THRESHOLD[4])
        # myColour = QtGui.QColor('#de4f05')
        myColour = QtGui.QColor(LINE_INTENSITY_COLOR[3])
        mySymbol4 = QgsSymbolV2.defaultSymbol(self.layer.geometryType())
        mySymbol4.symbolLayer(0).setRenderingPass(4)
        mySymbol4.setColor(myColour)
        mySymbol4.setAlpha(1)
        mySymbol4.setWidth(1)
        myRange4 = QgsRendererRangeV2(myMin, myMax, mySymbol4, myLabel)
        myRangeList.append(myRange4)
        
        # symbol 3
        myMin = LINE_INTENSITY_THRESHOLD[2]
        myMax = LINE_INTENSITY_THRESHOLD[3]
        myLabel = str(LINE_INTENSITY_THRESHOLD[2]) + ' - ' + str(LINE_INTENSITY_THRESHOLD[3])
        # myColour = QtGui.QColor('#fd9243')
        myColour = QtGui.QColor(LINE_INTENSITY_COLOR[2])
        mySymbol3 = QgsSymbolV2.defaultSymbol(self.layer.geometryType())
        mySymbol3.symbolLayer(0).setRenderingPass(3)
        mySymbol3.setColor(myColour)
        mySymbol3.setAlpha(1)
        mySymbol3.setWidth(0.8)
        myRange3 = QgsRendererRangeV2(myMin, myMax, mySymbol3, myLabel)
        myRangeList.append(myRange3)
        
        # symbol 2
        myMin = LINE_INTENSITY_THRESHOLD[1]
        myMax = LINE_INTENSITY_THRESHOLD[2]
        myLabel = str(LINE_INTENSITY_THRESHOLD[1]) + ' - ' + str(LINE_INTENSITY_THRESHOLD[2])
        # myColour = QtGui.QColor('#fdd1a5')
        myColour = QtGui.QColor(LINE_INTENSITY_COLOR[1])
        mySymbol2 = QgsSymbolV2.defaultSymbol(self.layer.geometryType())
        mySymbol2.symbolLayer(0).setRenderingPass(2)
        mySymbol2.setColor(myColour)
        mySymbol2.setAlpha(0.5)
        mySymbol2.setWidth(0.5)
        myRange2 = QgsRendererRangeV2(myMin, myMax, mySymbol2, myLabel)
        myRangeList.append(myRange2)
        
        # symbol 1
        myMin = LINE_INTENSITY_THRESHOLD[0]
        myMax = LINE_INTENSITY_THRESHOLD[1]
        myLabel = str(LINE_INTENSITY_THRESHOLD[0]) + ' - ' + str(LINE_INTENSITY_THRESHOLD[1])
        # myColour = QtGui.QColor('#fff5eb')
        myColour = QtGui.QColor(LINE_INTENSITY_COLOR[0])
        mySymbol1 = QgsSymbolV2.defaultSymbol(self.layer.geometryType())
        mySymbol1.symbolLayer(0).setRenderingPass(1)
        mySymbol1.setColor(myColour)
        mySymbol1.setAlpha(0.2)
        mySymbol1.setWidth(0)
        myRange1 = QgsRendererRangeV2(myMin, myMax, mySymbol1, myLabel)
        myRangeList.append(myRange1)
        
        self.myRenderer = QgsGraduatedSymbolRendererV2('', myRangeList)
        self.myRenderer.setMode(QgsGraduatedSymbolRendererV2.EqualInterval)
        
        
        
        
    # 设置图层渲染等级，失败，不起作用
    def setDefaultLevels(self):
        lineSymbols = self.layer.rendererV2().legendSymbolItemsV2();
        for lineSymbol in lineSymbols:
            sym = lineSymbol.symbol()
            for i in range(sym.symbolLayerCount()):
                sym.symbolLayer(i).setRenderingPass(5 - i)
        
        
    # 时序值改变时触发的方法：修改图层渲染属性
    def timeSliderChanged(self, value=None):
        if value == None:
            value = self.dock.horizontalTimeSlider.value() 
            
        if value <= self.dock.horizontalTimeSlider.maximum():
            self.myRenderer.setClassAttribute('h' + str(value))
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
            self.dock.horizontalTimeSlider.setValue(self.dock.horizontalTimeSlider.minimum())
            
        
        
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
        if value == self.dock.horizontalTimeSlider.maximum():
            self.qTimer.stop()
            self.dock.horizontalTimeSlider.setValue(self.dock.horizontalTimeSlider.minimum())
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
            myColour = QtGui.QColor('#1b1b1b')
        else:
            myColour = QtGui.QColor('#1b1b1b')
        # mySymbol1 = QgsSymbolV2.defaultSymbol(self.regionLayer.geometryType())
        mySymbol1 = QgsFillSymbolV2.createSimple(
            {'outline_width':u'0.1', 'outline_color':u'35,212,231,255', 'color':u'27,27,27,255'})
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
        mySymbol2 = QgsFillSymbolV2.createSimple(
            {'outline_width':u'0.1', 'outline_color':u'35,212,231,255', 'color':u'27,27,27,255'})
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
        mySymbol3 = QgsFillSymbolV2.createSimple(
            {'outline_width':u'0.1', 'outline_color':u'35,212,231,255', 'color':u'27,27,27,255'})
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
        mySymbol4 = QgsFillSymbolV2.createSimple(
            {'outline_width':u'0.1', 'outline_color':u'35,212,231,255', 'color':u'27,27,27,255'})
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
        mySymbol5 = QgsFillSymbolV2.createSimple(
            {'outline_width':u'0.1', 'outline_color':u'35,212,231,255', 'color':u'27,27,27,255'})
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
        mySymbol6 = QgsFillSymbolV2.createSimple(
            {'outline_width':u'0.1', 'outline_color':u'35,212,231,255', 'color':u'27,27,27,255'})
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
        mySymbol7 = QgsFillSymbolV2.createSimple(
            {'outline_width':u'0.1', 'outline_color':u'35,212,231,255', 'color':u'27,27,27,255'})
        mySymbol7.setColor(myColour)
        mySymbol7.setAlpha(1)
        # mySymbol7.setWidth(1.3)
        myRange7 = QgsRendererRangeV2(myMin, myMax, mySymbol7, myLabel)
        myRangeList.append(myRange7)
        
        
        defaultSymbol = QgsFillSymbolV2.createSimple(
            {'outline_width':u'0.1', 'outline_color':u'35,212,231,255', 'color':u'27,27,27,255'})
        
        self.myPolygonRenderer = QgsGraduatedSymbolRendererV2('', myRangeList)
        self.myPolygonRenderer.setMode(QgsGraduatedSymbolRendererV2.EqualInterval)
        self.myPolygonRenderer.setSourceSymbol(defaultSymbol)
        
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
            
        if value <= self.dock.horizontalTimeSlider.maximum():
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
            self.dock.horizontalTimeSlider.setValue(self.dock.horizontalTimeSlider.minimum())
        pass
    
    
    def showBroswerDialog(self):
        self.broswerDialog = uic.loadUi(os.path.join(self.path, BROSWER_DIALOG))
        
#         self.broswerDialog.show()
#         self.broswerDialog.webView.load(QUrl("file:///C:/Users/jj/Desktop/pyqt_broswer/svg.html"))
#         self.broswerDialog.webView.show()
        url = QUrl("C:/Users/jj/.qgis2/python/plugins/timemanager/broswer/svg.html");
        #url.addQueryItem("abc", "123");
        QDesktopServices.openUrl(url);
        
        
        
        
        
        
    # 显示选择目录对话框
    def showSelectDirectoryDialog(self):
        if self.setFlag == 0:
            self.selectDirectoryDialog = uic.loadUi(os.path.join(self.path, SELECT_DIRECTORY_DIALOG))
            self.selectDirectoryDialog.lineEdit.clear()
            self.selectDirectoryDialog.pushButton.clicked.connect(self.select_dictionary)
            self.selectDirectoryDialog.button_box.accepted.connect(self.loadCsvFiles)
            self.selectDirectoryDialog.show()
        else:
            self.setTrajectoryTimeSlider()
    
    def select_dictionary(self):
        filepath = QFileDialog.getExistingDirectory(self.selectDirectoryDialog, self.tr(u'select a dictionary'),
                                                    "C:\Users",
                                                    QFileDialog.ShowDirsOnly 
                                                    | QFileDialog.DontResolveSymlinks)
        # print filepath
        if filepath.strip():
            self.selectDirectoryDialog.lineEdit.setText(filepath)
            
    
    def loadCsvFiles(self):
        # 清除画布上的所有图层
        # QgsMapLayerRegistry.instance().removeAllMapLayers()
        
        # 图标样式，圆，大小设为1
        # symbol = QgsMarkerSymbolV2.createSimple({'name':'circle', 'size':'1'})
        
        self.filepath = self.selectDirectoryDialog.lineEdit.text()
        
        # 获取文件夹中的所有文件，并过滤不是csv格式的文件
        files = os.listdir(self.filepath)
        flag = 0
        for file in files:
            if not os.path.isdir(file) and '_0.csv' in file and not file.startswith('.') :
                uri1 = "file:///" + self.filepath + "/" + file + "?delimiter=%s&crs=epsg:4326&xField=%s&yField=%s" % (",", "longitude", "latitude")
                uri2 = "file:///" + self.filepath + "/" + "00_1.csv" + "?delimiter=%s&crs=epsg:4326&xField=%s&yField=%s" % (",", "longitude", "latitude")
                self.file = file
                self.vlayer1 = QgsVectorLayer(uri1, os.path.splitext(file)[0], "delimitedtext")
                self.vlayer2 = QgsVectorLayer(uri2, "00_1", "delimitedtext")
                self.vlayer1.rendererV2().symbol().setSize(1.0);
                self.vlayer2.rendererV2().symbol().setSize(1.0);
                self.vlayer1.rendererV2().symbol().setColor(QtGui.QColor('#ffff15'));
                self.vlayer2.rendererV2().symbol().setColor(QtGui.QColor('#fb01ff'));
                if self.vlayer1.isValid() and self.vlayer2.isValid():
                    QgsMapLayerRegistry.instance().addMapLayer(self.vlayer1)
                    QgsMapLayerRegistry.instance().addMapLayer(self.vlayer2)
                    
                    self.vl = QgsVectorLayer("LineString?crs=epsg:4326","od_lines", "memory")
                    pr = self.vl.dataProvider()
                    features = []
                    
                    csv_reader = csv.reader(open(self.filepath + "\\" + file, 'r+'))
                    count = 1
                    for row in csv_reader:
                        if count == 1:
                            count = 2
                            continue
                        fet = QgsFeature()
                        fet.setGeometry(QgsGeometry.fromPolyline([
                            QgsPoint(float(row[2]), float(row[3])), 
                            QgsPoint(float(row[8]), float(row[9]))]))
                        features.append(fet)
                    [res, outFeats] = pr.addFeatures(features)
                    
                    if not res:
                        QMessageBox.information(self.iface.mainWindow(), 'Error',
                                            "添加要素失败")
                    #self.iface.mapCanvas().refresh()
                    QgsMapLayerRegistry.instance().addMapLayer(self.vl)
                    
                    flag = 1
                    break
        if flag == 0:
            QMessageBox.information(self.iface.mainWindow(), 'Error',
                                    u'文件夹中没有初始文件（以_0.csv结尾的文件）')
        else:
            self.setTrajectoryTimeSlider()
            
    def setTrajectoryTimeSlider(self):
        if self.setFlag == 0:
            self.setFlag = 1
            self.dock.pushButtonOptions.setDisabled(True)
            self.dock.dateTimeEditCurrentTime.setDisabled(True)
            self.dock.pushButtonOdAnalysis.setDisabled(True)
            self.dock.pushButtonBack.setDisabled(True)
            self.dock.pushButtonForward.setDisabled(True)
            self.dock.spinBoxTimeExtent.setValue(1)
            self.setTimeFrameType(u'分钟')
            
            self.dock.spinBoxTimeExtent.setDisabled(True)
            self.dock.comboBoxTimeExtent.setDisabled(True)
            self.dock.pushButtonSetTimeSlider.setDisabled(True)
            self.dock.pushButtonSetPolygonTimeSlider.setDisabled(True)
            self.initTrajectoryTimeSlider()
            
            # 当设置为时序控制时绑定不同的触发方法
            self.dock.horizontalTimeSlider.valueChanged.connect(self.TrajectoryTimeSliderChanged)
            self.dock.pushButtonPlay.clicked.connect(self.autoPlay)
            
            self.dock.pushButtonSetTrajectorySlider.setText(u"取消设置")
            
            self.signalTimeFrameType.emit(u'分钟')
            
            
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
            self.dock.pushButtonSetPolygonTimeSlider.setDisabled(False)
            
            self.dock.pushButtonSetTrajectorySlider.setText(u"设置轨迹点时序")
            
            # self.qTimer = None
            # self.layer = None
            self.dock.horizontalTimeSlider.valueChanged.connect(self.currentTimeChangedSlider)
            self.dock.pushButtonPlay.clicked.connect(self.playClicked)
            
    def initTrajectoryTimeSlider(self):
        min = 0
        max = 287
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
        
    def TrajectoryTimeSliderChanged(self, value = None):
        if value == None:
            value = self.dock.horizontalTimeSlider.value() 
        
        if value <= self.dock.horizontalTimeSlider.maximum():
            
            # file = os.path.splitext(self.file)[0].split('_')[0] + "_" + str(value)
            hour1 = value / 12
            if value < 287 :
                hour2 = (value + 1) / 12
            else:
                hour2 = hour1
                
            num1 = value % 12
            if value < 287 :
                num2 = (value + 1) % 12
            else:
                num2 = num1
            
            if hour1 < 10:
                file1 = "0" + str(hour1) + "_" + str(num1)
            else:
                file1 = str(hour1) + "_" + str(num1)
                
            if hour2 < 10:
                file2 = "0" + str(hour2) + "_" + str(num2)
            else:
                file2 = str(hour2) + "_" + str(num2)
            
#             try :
            uri1 = "file:///" + self.filepath + "/" + file1 + ".csv" + "?delimiter=%s&crs=epsg:4326&xField=%s&yField=%s" % (",", "longitude", "latitude")
            uri2 = "file:///" + self.filepath + "/" + file2 + ".csv" + "?delimiter=%s&crs=epsg:4326&xField=%s&yField=%s" % (",", "longitude", "latitude")
            self.vlayer1.setDataSource(uri1, file1, "delimitedtext")
            self.vlayer2.setDataSource(uri2, file2, "delimitedtext")
#             self.regionLayer.triggerRepaint()
#             self.iface.legendInterface().refreshLayerSymbology(self.regionLayer)


            # 绘制轨迹连线
            # self.vl = QgsVectorLayer("LineString?crs=epsg:4326","od_lines", "memory")
            pr = self.vl.dataProvider()
            pr.deleteFeatures(self.vl.allFeatureIds())
            features = []
            
            csv_reader = csv.reader(open(self.filepath + "\\" + file1 + ".csv", 'r+'))
            count = 1
            for row in csv_reader:
                if count == 1:
                    count = 2
                    continue
                fet = QgsFeature()
                fet.setGeometry(QgsGeometry.fromPolyline([
                    QgsPoint(float(row[2]), float(row[3])), 
                    QgsPoint(float(row[8]), float(row[9]))]))
                features.append(fet)
            [res, outFeats] = pr.addFeatures(features)
            
            if not res:
                QMessageBox.information(self.iface.mainWindow(), 'Error',
                                    "添加要素失败")
            self.iface.mapCanvas().refresh()
            self.vl.triggerRepaint()
            self.iface.legendInterface().refreshLayerSymbology(self.vl)
            #QgsMapLayerRegistry.instance().addMapLayer(self.vl)
                
#             except :
#                 self.qTimer.stop()
#                 self.dock.horizontalTimeSlider.setValue(self.dock.horizontalTimeSlider.minimum())
            
        else:
            self.qTimer.stop()
            self.dock.horizontalTimeSlider.setValue(self.dock.horizontalTimeSlider.minimum())
        pass
    
    
    
    """
                        海洋数据
    """
    
    
    
    # 模式变化
    def currentModeChanged(self, mode):
        if mode == u'浮动车数据':
            self.dock.pushButtonSetTimeSlider.show()
            self.dock.pushButtonSetPolygonTimeSlider.show()
            # self.dock.radioButton_origin.show()
            # self.dock.radioButton_destination.show()
            self.dock.pushButtonSetTrajectorySlider.show()
            self.dock.pushButtonBroswerDialog.show()
            self.dock.pushButtonMarineOD.hide()
            self.dock.pushButtonPhone.hide()
        elif mode == u'海洋数据':
            self.dock.pushButtonSetTimeSlider.hide()
            self.dock.pushButtonSetPolygonTimeSlider.hide()
            self.dock.radioButton_origin.hide()
            self.dock.radioButton_destination.hide()
            self.dock.pushButtonSetTrajectorySlider.hide()
            self.dock.pushButtonBroswerDialog.hide()
            self.dock.pushButtonMarineOD.show()
            self.dock.pushButtonPhone.hide()
        elif mode == u'手机数据':
            self.dock.pushButtonSetTimeSlider.hide()
            self.dock.pushButtonSetPolygonTimeSlider.hide()
            self.dock.radioButton_origin.hide()
            self.dock.radioButton_destination.hide()
            self.dock.pushButtonSetTrajectorySlider.hide()
            self.dock.pushButtonBroswerDialog.hide()
            self.dock.pushButtonMarineOD.hide()
            self.dock.pushButtonPhone.show()
    
    def showSelectDirectoryDialog_marine(self):
        self.selectDirectoryDialog = uic.loadUi(os.path.join(self.path, SELECT_DIRECTORY_DIALOG))
        self.selectDirectoryDialog.lineEdit.clear()
        self.selectDirectoryDialog.pushButton.clicked.connect(self.select_dictionary)
        self.selectDirectoryDialog.button_box.accepted.connect(self.loadMarineFiles)
        self.selectDirectoryDialog.show()
        
    def loadMarineFiles(self):
        self.filepath = self.selectDirectoryDialog.lineEdit.text()
        files = os.listdir(self.filepath)
        
        flag = 0
        for file in files:
            if not os.path.isdir(files[0]) and "01-01" in file and not file.startswith('.') :
                flag = 1
                self.year = int(file.split("-")[0])
                uri1 = "file:///" + self.filepath + "/" + file + "?delimiter=%s&crs=epsg:4326&xField=%s&yField=%s" % (",", "origin_longitude", "origin_latitude")
                uri2 = "file:///" + self.filepath + "/" + file + "?delimiter=%s&crs=epsg:4326&xField=%s&yField=%s" % (",", "destination_longitude", "destination_latitude")
                self.file = file
                self.vlayer1 = QgsVectorLayer(uri1, os.path.splitext(file)[0] + "_o", "delimitedtext")
                self.vlayer2 = QgsVectorLayer(uri2, os.path.splitext(file)[0] + "_d", "delimitedtext")
                self.vlayer1.rendererV2().symbol().setSize(1.0);
                self.vlayer2.rendererV2().symbol().setSize(1.0);
                self.vlayer1.rendererV2().symbol().setColor(QtGui.QColor('#ffff15'));
                self.vlayer2.rendererV2().symbol().setColor(QtGui.QColor('#fb01ff'));
                if self.vlayer1.isValid() and self.vlayer2.isValid():
                    QgsMapLayerRegistry.instance().addMapLayer(self.vlayer1)
                    QgsMapLayerRegistry.instance().addMapLayer(self.vlayer2)
                    
                    self.vl = QgsVectorLayer("LineString?crs=epsg:4326","od_lines", "memory")
                    pr = self.vl.dataProvider()
                    features = []
                    
                    csv_reader = csv.reader(open(self.filepath + "\\" + file, 'r+'))
                    count = 1
                    for row in csv_reader:
                        if count == 1:
                            count = 2
                            continue
                        fet = QgsFeature()
                        fet.setGeometry(QgsGeometry.fromPolyline([
                            QgsPoint(float(row[len(row) - 4]), float(row[len(row) - 3])), 
                            QgsPoint(float(row[len(row) - 2]), float(row[len(row) - 1]))]))
                        features.append(fet)
                    [res, outFeats] = pr.addFeatures(features)
                    
                    if not res:
                        QMessageBox.information(self.iface.mainWindow(), 'Error',
                                            "添加要素失败")
                    #self.iface.mapCanvas().refresh()
                    QgsMapLayerRegistry.instance().addMapLayer(self.vl)
                    break
        
        if flag == 0:
            QMessageBox.information(self.iface.mainWindow(), 'Error',
                                    u'文件夹中没有初始文件（以_0.csv结尾的文件）')
        else:
            self.initMarineTimeSlider(self.year)
            self.dock.horizontalTimeSlider.valueChanged.connect(self.marineTimeSliderChanged)
            self.dock.pushButtonPlay.clicked.connect(self.autoPlay)
    
    def initMarineTimeSlider(self, year):
        if (year % 400 == 0) or ((year % 4 == 0) and (year % 100 != 0)):
            max = 366
        else:
            max = 365
        
        min = 1
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
        
    def marineTimeSliderChanged(self, value = None):
        try :
            if value == None:
                value = self.dock.horizontalTimeSlider.value() 
            
            if value <= self.dock.horizontalTimeSlider.maximum():
                date = DateTransform.number2date(self.year, value)
                uri1 = "file:///" + self.filepath + "/" + date + ".csv" + "?delimiter=%s&crs=epsg:4326&xField=%s&yField=%s" % (",", "origin_longitude", "origin_latitude")
                uri2 = "file:///" + self.filepath + "/" + date + ".csv" + "?delimiter=%s&crs=epsg:4326&xField=%s&yField=%s" % (",", "destination_longitude", "destination_latitude")
                self.vlayer1.setDataSource(uri1, date + "_o", "delimitedtext")
                self.vlayer2.setDataSource(uri2, date + "_d", "delimitedtext")
                # 绘制轨迹连线
                # self.vl = QgsVectorLayer("LineString?crs=epsg:4326","od_lines", "memory")
                pr = self.vl.dataProvider()
                pr.deleteFeatures(self.vl.allFeatureIds())
                features = []
                
                csv_reader = csv.reader(open(self.filepath + "\\" + date + ".csv", 'r+'))
                count = 1
                for row in csv_reader:
                    if count == 1:
                        count = 2
                        continue
                    fet = QgsFeature()
                    fet.setGeometry(QgsGeometry.fromPolyline([
                        QgsPoint(float(row[len(row) - 4]), float(row[len(row) - 3])), 
                        QgsPoint(float(row[len(row) - 2]), float(row[len(row) - 1]))]))
                    features.append(fet)
                [res, outFeats] = pr.addFeatures(features)
                
                if not res:
                    QMessageBox.information(self.iface.mainWindow(), 'Error',
                                        "添加要素失败")
                self.iface.mapCanvas().refresh()
                self.vl.triggerRepaint()
                self.iface.legendInterface().refreshLayerSymbology(self.vl)
                #QgsMapLayerRegistry.instance().addMapLayer(self.vl)
                    
    #             except :
    #                 self.qTimer.stop()
    #                 self.dock.horizontalTimeSlider.setValue(self.dock.horizontalTimeSlider.minimum())
            else:
                self.qTimer.stop()
                self.dock.horizontalTimeSlider.setValue(self.dock.horizontalTimeSlider.minimum())
        except Exception as e:
            QMessageBox.information(self.iface.mainWindow(), 'Error',
                                        e.args)
            print(e.args)
            self.qTimer.stop()
            self.dock.horizontalTimeSlider.setValue(self.dock.horizontalTimeSlider.minimum())
            
        
        
        
        
        
        
    # 手机数据处理
    def showSelectDirectoryDialog_phone(self):
        self.selectDirectoryDialog = uic.loadUi(os.path.join(self.path, SELECT_DIRECTORY_DIALOG))
        self.selectDirectoryDialog.lineEdit.clear()
        self.selectDirectoryDialog.pushButton.clicked.connect(self.select_dictionary)
        self.selectDirectoryDialog.button_box.accepted.connect(self.loadPhoneFiles)
        self.selectDirectoryDialog.show()
        
    def loadPhoneFiles(self):
        self.filepath = self.selectDirectoryDialog.lineEdit.text()
        files = os.listdir(self.filepath)

        flag = 0
        for file in files:
            if not os.path.isdir(files[0]) and "0_0" in file and not file.startswith('.') :
                flag = 1
                uri1 = "file:///" + self.filepath + "/" + file + "?delimiter=%s&crs=epsg:4326&xField=%s&yField=%s" % (",", "Lng", "Lat")
#                 uri2 = "file:///" + self.filepath + "/" + file + "?delimiter=%s&crs=epsg:4326&xField=%s&yField=%s" % (",", "destination_longitude", "destination_latitude")
                self.file = file
                self.vlayer1 = QgsVectorLayer(uri1, os.path.splitext(file)[0], "delimitedtext")
                self.vlayer1.rendererV2().symbol().setSize(1.0);
                self.vlayer1.rendererV2().symbol().setColor(QtGui.QColor('#ffff15'));
                if self.vlayer1.isValid():
                    QgsMapLayerRegistry.instance().addMapLayer(self.vlayer1)
                    break
        
        if flag == 0:
            QMessageBox.information(self.iface.mainWindow(), 'Error',
                                u'文件夹中没有初始文件（以_0.csv结尾的文件）')
        else:
            self.initPhoneTimeSlider()
            self.dock.horizontalTimeSlider.valueChanged.connect(self.phoneTimeSliderChanged)
            self.dock.pushButtonPlay.clicked.connect(self.autoPlay)
            
#         self.filepath = self.selectDirectoryDialog.lineEdit.text()
#         dirs = os.listdir(self.filepath)
#         
#         self.filepaths = {}
#         self.vlayers = {}
#         index = 1
#         
#         for dir in dirs:
#             
#             if not os.path.isdir(self.filepath + '/' + dir):
#                 continue
#             
#             # 存储文件夹名称
#             self.filepaths[index] = dir 
#             
#             files = os.listdir(self.filepath + '/' + dir)
#             flag = 0
#             for file in files:
#                 if not os.path.isdir(files[0]) and "0_0" in file and not file.startswith('.') :
#                     flag = 1
#                     uri = "file:///" + self.filepath + "/" + dir + "/" + file + "?delimiter=%s&crs=epsg:4326&xField=%s&yField=%s" % (",", "Lng", "Lat")
#     #                 uri2 = "file:///" + self.filepath + "/" + file + "?delimiter=%s&crs=epsg:4326&xField=%s&yField=%s" % (",", "destination_longitude", "destination_latitude")
#                     vlayer = QgsVectorLayer(uri, dir + '_' + os.path.splitext(file)[0], "delimitedtext")
#                     vlayer.rendererV2().symbol().setSize(1.0)
# #                     vlayer.rendererV2().symbol().setColor(QtGui.QColor('#ffff15'));
#                     if vlayer.isValid():
#                         QgsMapLayerRegistry.instance().addMapLayer(vlayer)
#                         # 存储图层
#                         self.vlayers[index] = vlayer
#                         break
#             
#             index = index + 1
#             if flag == 0:
#                 QMessageBox.information(self.iface.mainWindow(), 'Error',
#                                         u'文件夹中没有初始文件（以_0.csv结尾的文件）')
#             else:
#                 self.initPhoneTimeSlider()
#                 self.dock.horizontalTimeSlider.valueChanged.connect(self.phoneTimeSliderChanged)
#                 self.dock.pushButtonPlay.clicked.connect(self.autoPlay)
            
    
    def initPhoneTimeSlider(self):
        min = 0
        max = 287
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
        
        
    def phoneTimeSliderChanged(self, value = None):
        try :
            if value == None:
                value = self.dock.horizontalTimeSlider.value() 
            
            if value <= self.dock.horizontalTimeSlider.maximum():
                
                # file = os.path.splitext(self.file)[0].split('_')[0] + "_" + str(value)
                hour1 = value / 12
    #             if value < 287 :
    #                 hour2 = (value + 1) / 12
    #             else:
    #                 hour2 = hour1
                    
                num1 = value % 12
    #             if value < 287 :
    #                 num2 = (value + 1) % 12
    #             else:
    #                 num2 = num1
                
    #             if hour1 < 10:
    #                 file1 = "0" + str(hour1) + "_" + str(num1)
    #             else:
                file1 = str(hour1) + "_" + str(num1)
                    
    #             if hour2 < 10:
    #                 file2 = "0" + str(hour2) + "_" + str(num2)
    #             else:
    #                 file2 = str(hour2) + "_" + str(num2)
                
    #             try :
                uri1 = "file:///" + self.filepath + "/" + file1 + ".csv" + "?delimiter=%s&crs=epsg:4326&xField=%s&yField=%s" % (",", "Lng", "Lat")
    #             uri2 = "file:///" + self.filepath + "/" + file2 + ".csv" + "?delimiter=%s&crs=epsg:4326&xField=%s&yField=%s" % (",", "longitude", "latitude")
                self.vlayer1.setDataSource(uri1, file1, "delimitedtext")
    #             self.vlayer2.setDataSource(uri2, file2, "delimitedtext")
    #             self.regionLayer.triggerRepaint()
    #             self.iface.legendInterface().refreshLayerSymbology(self.regionLayer)
    
    
                # 绘制轨迹连线
                # self.vl = QgsVectorLayer("LineString?crs=epsg:4326","od_lines", "memory")
    #             pr = self.vl.dataProvider()
    #             pr.deleteFeatures(self.vl.allFeatureIds())
    #             features = []
                
    #             csv_reader = csv.reader(open(self.filepath + "\\" + file1 + ".csv", 'r+'))
    #             count = 1
    #             for row in csv_reader:
    #                 if count == 1:
    #                     count = 2
    #                     continue
    #                 fet = QgsFeature()
    #                 fet.setGeometry(QgsGeometry.fromPolyline([
    #                     QgsPoint(float(row[2]), float(row[3])), 
    #                     QgsPoint(float(row[8]), float(row[9]))]))
    #                 features.append(fet)
    #             [res, outFeats] = pr.addFeatures(features)
                
#                 self.iface.mapCanvas().refresh()
    #             self.vl.triggerRepaint()
    #             self.iface.legendInterface().refreshLayerSymbology(self.vl)
                #QgsMapLayerRegistry.instance().addMapLayer(self.vl)
                    
    #             except :
    #                 self.qTimer.stop()
    #                 self.dock.horizontalTimeSlider.setValue(self.dock.horizontalTimeSlider.minimum())
                
            else:
                self.qTimer.stop()
                self.dock.horizontalTimeSlider.setValue(self.dock.horizontalTimeSlider.minimum())
        except Exception as e:
            QMessageBox.information(self.iface.mainWindow(), 'Error', e.args)
#             print(e.args)
            self.qTimer.stop()
            self.dock.horizontalTimeSlider.setValue(self.dock.horizontalTimeSlider.minimum())
    
    
    



    # 冯博数据处理程序
    def showInputParameterDialog(self):
        self.inputParameterDialog = uic.loadUi(os.path.join(self.path, INPUT_PARAMETER_MC_DIALOG))
        self.inputParameterDialog.obq_selectDataPath.clicked.connect(self.mc_select_dictionary)
        self.inputParameterDialog.rbq_selectDataPath.clicked.connect(self.mc_select_dictionary)
        self.inputParameterDialog.pq_selectDataPath.clicked.connect(self.mc_select_dictionary)
        self.inputParameterDialog.obq_comboBox.currentIndexChanged[str].connect(
            self.obq_function_changed)
        
        
        self.inputParameterDialog.label_15.show()
        self.inputParameterDialog.pq_min_distance.show()
        self.inputParameterDialog.pq_max_distance.show()
        self.inputParameterDialog.label_16.show()
        self.inputParameterDialog.label_14.hide()
        self.inputParameterDialog.label_8.hide()
        self.inputParameterDialog.pq_max_angle.hide()
        self.inputParameterDialog.pq_min_angle.hide()
        self.inputParameterDialog.label_13.hide()
        self.inputParameterDialog.pq_forward.hide()
        self.inputParameterDialog.pq_reversion.hide()
        self.inputParameterDialog.pq_comboBox.currentIndexChanged[str].connect(
            self.pq_function_changed)
        
        self.inputParameterDialog.buttonBox.accepted.connect(self.validateParameter)
        self.inputParameterDialog.show()
    
    # 打开文件夹选择窗口
    def mc_select_dictionary(self):
        filepath = QFileDialog.getExistingDirectory(self.inputParameterDialog, self.tr(u'select a dictionary'),
                                                    "C:\Users",
                                                    QFileDialog.ShowDirsOnly 
                                                    | QFileDialog.DontResolveSymlinks)
        # print filepath
        if filepath.strip():
            currentIndex = self.inputParameterDialog.tabWidget.currentIndex()
            if currentIndex == 0:
                self.inputParameterDialog.obq_dataPath.setText(filepath)
            if currentIndex == 1:
                self.inputParameterDialog.rbq_dataPath.setText(filepath)
            if currentIndex == 2:
                self.inputParameterDialog.pq_dataPath.setText(filepath)
            if currentIndex == 3:
                self.inputParameterDialog.trajectory_dataPath.setText(filepath)
    
    '''根据下拉框选项选择显示参数'''
    def obq_function_changed(self, function):
        if function == 'ExtractPoint':
            self.inputParameterDialog.label_2.show()
            self.inputParameterDialog.obq_refObject.show()
            self.inputParameterDialog.label_3.show()
            self.inputParameterDialog.obq_targetObject.show()
            self.inputParameterDialog.label_5.show()
            self.inputParameterDialog.obq_time.show()
        elif function == 'TimeDrilling':
            self.inputParameterDialog.label_2.show()
            self.inputParameterDialog.obq_refObject.show()
            self.inputParameterDialog.label_3.show()
            self.inputParameterDialog.obq_targetObject.show()
            self.inputParameterDialog.label_5.hide()
            self.inputParameterDialog.obq_time.hide()
        elif function == 'TargetDrilling':
            self.inputParameterDialog.label_2.show()
            self.inputParameterDialog.obq_refObject.show()
            self.inputParameterDialog.label_3.hide()
            self.inputParameterDialog.obq_targetObject.hide()
            self.inputParameterDialog.label_5.show()
            self.inputParameterDialog.obq_time.show()
        elif function == 'TimeCutting':
            self.inputParameterDialog.label_2.hide()
            self.inputParameterDialog.obq_refObject.hide()
            self.inputParameterDialog.label_3.hide()
            self.inputParameterDialog.obq_targetObject.hide()
            self.inputParameterDialog.label_5.show()
            self.inputParameterDialog.obq_time.show()
        elif function == 'ReferecenCutting':
            self.inputParameterDialog.label_2.show()
            self.inputParameterDialog.obq_refObject.show()
            self.inputParameterDialog.label_3.hide()
            self.inputParameterDialog.obq_targetObject.hide()
            self.inputParameterDialog.label_5.hide()
            self.inputParameterDialog.obq_time.hide()
    
    '''根据下拉框选项选择显示参数'''
    def pq_function_changed(self, function):
        if function == 'Intimate Contact':
            self.inputParameterDialog.label_15.show()
            self.inputParameterDialog.pq_min_distance.show()
            self.inputParameterDialog.pq_max_distance.show()
            self.inputParameterDialog.label_16.show()
            self.inputParameterDialog.label_14.hide()
            self.inputParameterDialog.label_8.hide()
            self.inputParameterDialog.pq_max_angle.hide()
            self.inputParameterDialog.pq_min_angle.hide()
            self.inputParameterDialog.label_13.hide()
            self.inputParameterDialog.pq_forward.hide()
            self.inputParameterDialog.pq_reversion.hide()
            
        elif function == 'Closer Object':
            self.inputParameterDialog.label_15.hide()
            self.inputParameterDialog.pq_min_distance.hide()
            self.inputParameterDialog.pq_max_distance.hide()
            self.inputParameterDialog.label_16.hide()
            self.inputParameterDialog.label_14.hide()
            self.inputParameterDialog.label_8.hide()
            self.inputParameterDialog.pq_max_angle.hide()
            self.inputParameterDialog.pq_min_angle.hide()
            self.inputParameterDialog.label_13.hide()
            self.inputParameterDialog.pq_forward.hide()
            self.inputParameterDialog.pq_reversion.hide()
        elif function == 'Follower':
            self.inputParameterDialog.label_15.show()
            self.inputParameterDialog.pq_min_distance.show()
            self.inputParameterDialog.pq_max_distance.show()
            self.inputParameterDialog.label_16.show()
            self.inputParameterDialog.label_14.show()
            self.inputParameterDialog.label_8.show()
            self.inputParameterDialog.pq_max_angle.show()
            self.inputParameterDialog.pq_min_angle.show()
            self.inputParameterDialog.label_13.hide()
            self.inputParameterDialog.pq_forward.hide()
            self.inputParameterDialog.pq_reversion.hide()
        elif function == 'Trend Recognition':
            self.inputParameterDialog.label_15.hide()
            self.inputParameterDialog.pq_min_distance.hide()
            self.inputParameterDialog.pq_max_distance.hide()
            self.inputParameterDialog.label_16.hide()
            self.inputParameterDialog.label_14.hide()
            self.inputParameterDialog.label_8.hide()
            self.inputParameterDialog.pq_max_angle.hide()
            self.inputParameterDialog.pq_min_angle.hide()
            self.inputParameterDialog.label_13.show()
            self.inputParameterDialog.pq_forward.show()
            self.inputParameterDialog.pq_reversion.show()
    
    
    '''验证参数'''
    def validateParameter(self):
    
        # 调用查询程序dll
#         self.dll = ctypes.cdll.LoadLibrary(r'G:/mcCode/RelativeDataOperationDll.dll')
        dllPath = os.getcwd() + '/mcCode/RelativeDataOperationDll.dll'
        self.dll = ctypes.cdll.LoadLibrary(dllPath)
        
        # 删除原先图层
        try :
            self.dock.horizontalTimeSlider.valueChanged.disconnect()
        except:
            pass
        try :
            if not self.vl_refObject is None :
                QgsMapLayerRegistry.instance().removeMapLayer(self.vl_refObject.id())
        except:
            pass
        try :
            if not self.vl_targetObject is None :
                QgsMapLayerRegistry.instance().removeMapLayer(self.vl_targetObject.id())
        except:
            pass
        try :
            if not self.vl_trajectory is None :
                QgsMapLayerRegistry.instance().removeMapLayer(self.vl_trajectory.id())
        except:
            pass
        try :
            if not self.vl is None :
                QgsMapLayerRegistry.instance().removeMapLayer(self.vl.id())
        except:
            pass
        try :
            if not self.qTimer is None:
                self.qTimer.stop()
        except:
            pass
        
        ''' tab:object_based query'''
        currentIndex = self.inputParameterDialog.tabWidget.currentIndex()
        if currentIndex == 0:
            obq_dataPath = self.inputParameterDialog.obq_dataPath.text()
            obq_refObject = self.inputParameterDialog.obq_refObject.text()
            obq_targetObject = self.inputParameterDialog.obq_targetObject.text()
            obq_time = self.inputParameterDialog.obq_time.text()
            
            '''判断文件夹中文件数目，为0则提示错误'''
            self.getFilesNum(obq_dataPath)
            if self.filesNum == 0:
                QMessageBox.information(self.iface.mainWindow(), 'Error', u'文件夹中数据为空')
                return
            
            # 判断数据格式是否正确
            function = self.inputParameterDialog.obq_comboBox.currentText()
            if function == 'ExtractPoint':
                if obq_dataPath is None or obq_dataPath == "":
                    QMessageBox.information(self.iface.mainWindow(), 'Error', u'文件路径不能为空')
                    return
                if obq_refObject is None or obq_refObject == "":
                    QMessageBox.information(self.iface.mainWindow(), 'Error', u'参照对象不能为空')
                    return
                if obq_targetObject is None or obq_targetObject == "":
                    QMessageBox.information(self.iface.mainWindow(), 'Error', u'目标对象不能为空')
                    return
                if obq_time is None or obq_time == "":
                    QMessageBox.information(self.iface.mainWindow(), 'Error', u'时间不能为空')
                    return
                try:
                    if not (obq_time is None or obq_time == ""):
                        obq_time = int(obq_time)
                except:
                    QMessageBox.information(self.iface.mainWindow(), 'Error', u'时间格式不正确')
                    return
                
            elif function == 'TimeDrilling':
                if obq_dataPath is None or obq_dataPath == "":
                    QMessageBox.information(self.iface.mainWindow(), 'Error', u'文件路径不能为空')
                    return
                if obq_refObject is None or obq_refObject == "":
                    QMessageBox.information(self.iface.mainWindow(), 'Error', u'参照对象不能为空')
                    return
                if obq_targetObject is None or obq_targetObject == "":
                    QMessageBox.information(self.iface.mainWindow(), 'Error', u'目标对象不能为空')
                    return
            elif function == 'TargetDrilling':
                if obq_dataPath is None or obq_dataPath == "":
                    QMessageBox.information(self.iface.mainWindow(), 'Error', u'文件路径不能为空')
                    return
                if obq_refObject is None or obq_refObject == "":
                    QMessageBox.information(self.iface.mainWindow(), 'Error', u'参照对象不能为空')
                    return
                if obq_time is None or obq_time == "":
                    QMessageBox.information(self.iface.mainWindow(), 'Error', u'时间不能为空')
                    return
                try:
                    if not (obq_time is None or obq_time == ""):
                        obq_time = int(obq_time)
                except:
                    QMessageBox.information(self.iface.mainWindow(), 'Error', u'时间格式不正确')
                    return
            elif function == 'TimeCutting':
                if obq_dataPath is None or obq_dataPath == "":
                    QMessageBox.information(self.iface.mainWindow(), 'Error', u'文件路径不能为空')
                    return
                if obq_time is None or obq_time == "":
                    QMessageBox.information(self.iface.mainWindow(), 'Error', u'时间不能为空')
                    return
                try:
                    if not (obq_time is None or obq_time == ""):
                        obq_time = int(obq_time)
                except:
                    QMessageBox.information(self.iface.mainWindow(), 'Error', u'时间格式不正确')
                    return
            elif function == 'ReferecenCutting':
                if obq_dataPath is None or obq_dataPath == "":
                    QMessageBox.information(self.iface.mainWindow(), 'Error', u'文件路径不能为空')
                    return
                if obq_refObject is None or obq_refObject == "":
                    QMessageBox.information(self.iface.mainWindow(), 'Error', u'参照对象不能为空')
                    return
                
            self.newDockWidget()
            self.visualData_obq(obq_dataPath, obq_refObject, obq_targetObject, obq_time, function)
            
        ''' tab: relation-based query'''
        if currentIndex == 1:
            rbq_dataPath = self.inputParameterDialog.rbq_dataPath.text()
            rbq_refObject = self.inputParameterDialog.rbq_refObject.text()
            rbq_distance = self.inputParameterDialog.rbq_distance.text()
            rbq_time = self.inputParameterDialog.rbq_time.text()
            
            '''判断文件夹中文件数目，为0则提示错误'''
            self.getFilesNum(rbq_dataPath)
            if self.filesNum == 0:
                QMessageBox.information(self.iface.mainWindow(), 'Error', u'文件夹中数据为空')
                return
            
            # 判断数据格式是否正确
            if rbq_dataPath is None or rbq_dataPath == "":
                QMessageBox.information(self.iface.mainWindow(), 'Error', u'文件路径不能为空')
                return
            if rbq_refObject is None or rbq_refObject == "":
                QMessageBox.information(self.iface.mainWindow(), 'Error', u'参照对象不能为空')
                return
            if rbq_distance is None or rbq_distance == "":
                QMessageBox.information(self.iface.mainWindow(), 'Error', u'距离不能为空')
                return
            try:
                if not (rbq_time is None or rbq_time == ""):
                    rbq_time = int(rbq_time)
                else:
                    rbq_time = -1
            except:
                QMessageBox.information(self.iface.mainWindow(), 'Error', u'时间格式不正确')
                return
            
            self.dll.RelationshipExtracting.argtypes = [c_char_p,c_char_p,c_char_p,c_int,c_char_p]
            self.dll.RelationshipExtracting.restype = c_void_p
            self.dll.RelationshipExtracting(rbq_dataPath,rbq_refObject,"",int(rbq_time),rbq_distance)
            
            self.newDockWidget()
            self.dynamicScatter(rbq_dataPath)
            
        '''pattern query'''
        if currentIndex == 2:
            pq_dataPath = self.inputParameterDialog.pq_dataPath.text()
            pq_refObject = self.inputParameterDialog.pq_refObject.text()
            pq_min_distance = self.inputParameterDialog.pq_min_distance.text()
            pq_max_distance = self.inputParameterDialog.pq_max_distance.text()
            pq_min_angle = self.inputParameterDialog.pq_min_angle.text()
            pq_max_angle = self.inputParameterDialog.pq_max_angle.text()
            
            '''判断文件夹中文件数目，为0则提示错误'''
            self.getFilesNum(pq_dataPath)
            if self.filesNum == 0:
                QMessageBox.information(self.iface.mainWindow(), 'Error', u'文件夹中数据为空')
                return
            
            function = self.inputParameterDialog.pq_comboBox.currentText()
            if function == 'Intimate Contact':
                if pq_dataPath is None or pq_dataPath == "":
                    QMessageBox.information(self.iface.mainWindow(), 'Error', u'文件路径不能为空')
                    return
                if pq_refObject is None or pq_refObject == "":
                    QMessageBox.information(self.iface.mainWindow(), 'Error', u'参照对象不能为空')
                    return
                if pq_min_distance is None or pq_min_distance == "":
                    QMessageBox.information(self.iface.mainWindow(), 'Error', u'最小距离不能为空')
                    return
                if pq_max_distance is None or pq_max_distance == "":
                    QMessageBox.information(self.iface.mainWindow(), 'Error', u'最大距离不能为空')
                    return
            elif function == 'Closer Object':
                if pq_dataPath is None or pq_dataPath == "":
                    QMessageBox.information(self.iface.mainWindow(), 'Error', u'文件路径不能为空')
                    return
                if pq_refObject is None or pq_refObject == "":
                    QMessageBox.information(self.iface.mainWindow(), 'Error', u'参照对象不能为空')
                    return
                
                try:
                    if not (pq_min_distance is None or pq_min_distance == ""):
                        pq_min_distance = float(pq_min_distance)
                    if not (pq_max_distance is None or pq_max_distance == ""):
                        pq_max_distance = float(pq_max_distance)
                except:
                    QMessageBox.information(self.iface.mainWindow(), 'Error', u'数字格式不正确')
                    return
            elif function == 'Follower':
                if pq_dataPath is None or pq_dataPath == "":
                    QMessageBox.information(self.iface.mainWindow(), 'Error', u'文件路径不能为空')
                    return
                if pq_refObject is None or pq_refObject == "":
                    QMessageBox.information(self.iface.mainWindow(), 'Error', u'参照对象不能为空')
                    return
                if pq_min_distance is None or pq_min_distance == "":
                    QMessageBox.information(self.iface.mainWindow(), 'Error', u'最小距离不能为空')
                    return
                if pq_max_distance is None or pq_max_distance == "":
                    QMessageBox.information(self.iface.mainWindow(), 'Error', u'最大距离不能为空')
                    return
                if pq_min_angle is None or pq_min_angle == "":
                    QMessageBox.information(self.iface.mainWindow(), 'Error', u'最小角度不能为空')
                    return
                if pq_max_angle is None or pq_max_angle == "":
                    QMessageBox.information(self.iface.mainWindow(), 'Error', u'最大角度不能为空')
                    return
                try:
                    if not (pq_min_distance is None or pq_min_distance == ""):
                        pq_min_distance = float(pq_min_distance)
                    if not (pq_max_distance is None or pq_max_distance == ""):
                        pq_max_distance = float(pq_max_distance)
                    if not (pq_min_angle is None or pq_min_angle == ""):
                        pq_min_angle = float(pq_min_angle)
                    if not (pq_max_angle is None or pq_max_angle == ""):
                        pq_max_angle = float(pq_max_angle)
                except:
                    QMessageBox.information(self.iface.mainWindow(), 'Error', u'数字格式不正确')
                    return
            elif function == 'Trend Recognition':
                if pq_dataPath is None or pq_dataPath == "":
                    QMessageBox.information(self.iface.mainWindow(), 'Error', u'文件路径不能为空')
                    return
                if pq_refObject is None or pq_refObject == "":
                    QMessageBox.information(self.iface.mainWindow(), 'Error', u'参照对象不能为空')
                    return
            self.newDockWidget()
            self.visualData_pq(pq_dataPath, pq_refObject, pq_max_distance, 
                               pq_min_distance, pq_max_angle,pq_min_angle,function)
        '''轨迹显示'''
        if currentIndex == 3:
            trajectory_dataPath = self.inputParameterDialog.trajectory_dataPath.text()
            self.showTrajectory(trajectory_dataPath)
            
        
    '''新建dockWidget'''
    def newDockWidget(self):
        # 打开右侧数据显示窗口
        self.showResultDockWidget = uic.loadUi(os.path.join(self.path, SHOW_RESULT_DOCKWIDGET))
        headers = [u"时间",u"参照ID",u"目标ID",u"距离",u"角度"]
        self.showResultDockWidget.tableWidget.setColumnCount(5)
        self.showResultDockWidget.tableWidget.setHorizontalHeaderLabels(headers)
        self.showResultDockWidget.currentTime.hide()
        self.showResultDockWidget.closingNum.hide()
        self.showResultDockWidget.accelerateNum.hide()
        self.showResultDockWidget.decelerateNum.hide()
        self.showResultDockWidget.label_2.hide()
        self.showResultDockWidget.label_4.hide()
        self.showResultDockWidget.label_6.hide()
        self.showResultDockWidget.label_8.hide()
        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.showResultDockWidget)

    '''获取路径下的文件个数作为时序个数'''
    def getFilesNum(self, filePath):
        self.filesNum = len(os.listdir(filePath))
        
    '''object-based query'''
    def visualData_obq(self, dataPath, refObject, targetObject, time, function):
        
        if function == 'ExtractPoint':
            # 设置python调用c++代码
            self.dll.ExtractPoint.argtypes = [c_char_p,c_char_p,c_char_p,c_int]
            self.dll.ExtractPoint.restype = c_void_p
            self.dll.ExtractPoint(dataPath,refObject,targetObject,time)
            
            self.staticVisual_obq(dataPath)
        elif function == 'TimeDrilling':
            # 设置python调用c++代码
            self.dll.TimeDrilling.argtypes = [c_char_p,c_char_p,c_char_p]
            self.dll.TimeDrilling.restype = c_void_p
            self.dll.TimeDrilling(dataPath,refObject,targetObject)
            
            self.dynamicVisual_obq(dataPath)
        elif function == 'TargetDrilling':
            # 设置python调用c++代码
            self.dll.TargetDrilling.argtypes = [c_char_p,c_char_p,c_int]
            self.dll.TargetDrilling.restype = c_void_p
            self.dll.TargetDrilling(dataPath,refObject,time)
            
            self.staticVisual_obq(dataPath)
        elif function == 'TimeCutting':
            # 设置python调用c++代码
            self.dll.TimeCutting.argtypes = [c_char_p,c_int]
            self.dll.TimeCutting.restype = c_void_p
            self.dll.TimeCutting(dataPath,time)
            
            self.staticVisual_obq(dataPath)
        elif function == 'ReferecenCutting':
            # 设置python调用c++代码
            self.dll.ReferecenCutting.argtypes = [c_char_p,c_char_p]
            self.dll.ReferecenCutting.restype = c_void_p
            self.dll.ReferecenCutting(dataPath,refObject)
            
            self.dynamicVisual_obq(dataPath)
        
    '''静态obq'''
    def staticVisual_obq(self, dataPath):
         # 读取C++代码生成的文件，并进行可视化
        filepath = dataPath + "_result.csv"
        
        # 添加图层
        uri1 = "file:///" + filepath + "?delimiter=%s&crs=epsg:4326&xField=%s&yField=%s" % (",", "Lng1", "Lat1")
        uri2 = "file:///" + filepath + "?delimiter=%s&crs=epsg:4326&xField=%s&yField=%s" % (",", "Lng2", "Lat2")
        self.vl_refObject = QgsVectorLayer(uri1, "refObject", "delimitedtext")
        self.vl_targetObject = QgsVectorLayer(uri2, "targetObject", "delimitedtext")
        self.vl_refObject.rendererV2().symbol().setSize(3.0);
        self.vl_targetObject.rendererV2().symbol().setSize(1.0);
        self.vl_refObject.rendererV2().symbol().setColor(QtGui.QColor('#ffff15'));
        self.vl_targetObject.rendererV2().symbol().setColor(QtGui.QColor('#fb01ff'));
        if self.vl_refObject.isValid() and self.vl_targetObject.isValid():
            QgsMapLayerRegistry.instance().addMapLayer(self.vl_refObject)
            QgsMapLayerRegistry.instance().addMapLayer(self.vl_targetObject)
            
            self.vl = QgsVectorLayer("LineString?crs=epsg:4326","line", "memory")
            pr = self.vl.dataProvider()
            features = []
            
            with open(filepath) as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    fet = QgsFeature()
                    fet.setGeometry(QgsGeometry.fromPolyline([
                        QgsPoint(float(row['Lng1']), float(row['Lat1'])), 
                        QgsPoint(float(row['Lng2']), float(row['Lat2']))]))
                    features.append(fet)
                    
                    if not float(row['Dis']) == 0.0:
                        # 将数据显示到右侧表格中
                        self.showResultDockWidget.tableWidget.insertRow(
                            self.showResultDockWidget.tableWidget.rowCount())
                        r = self.showResultDockWidget.tableWidget.rowCount() - 1
                        self.showResultDockWidget.tableWidget.setItem(
                            r, 0, QTableWidgetItem(str(row['RealTime'])))
                        self.showResultDockWidget.tableWidget.setItem(
                            r, 1, QTableWidgetItem(str(row['strID_Ref'])))
                        self.showResultDockWidget.tableWidget.setItem(
                            r, 2, QTableWidgetItem(str(row['strID_Tar'])))
                        self.showResultDockWidget.tableWidget.setItem(
                            r, 3, QTableWidgetItem(str(row['Dis'])))
                        self.showResultDockWidget.tableWidget.setItem(
                            r, 4, QTableWidgetItem(str(row['Ang'])))
                
                
            [res, outFeats] = pr.addFeatures(features)
            
            if not res:
                QMessageBox.information(self.iface.mainWindow(), 'Error',
                                    u"添加要素失败")
            #self.iface.mapCanvas().refresh()
            QgsMapLayerRegistry.instance().addMapLayer(self.vl)
        else:
            QMessageBox.information(self.iface.mainWindow(), 'Error', u'图层加载失败')
            return
    '''动态obq'''
    def dynamicVisual_obq(self, dataPath):
        # 读取C++代码生成的文件，并进行可视化
        filepath = dataPath + "_result.csv"
            
        # 读取csv文件中的所有数据，用dict进行存储
        self.allData = {}
        
        '''初始化allData字典，每个value是列表，保存对应时间的记录'''
        for time in range(0,self.filesNum):
            self.allData[time] = {}
        
        # 保存所有已经遍历过的时间点
        self.traversedDataTime = []
        with open(filepath) as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                # 计算每时刻目标点和参照点的坐标差值，以方便显示相对位置
                row['delta_lng'] = float(row['Lng2']) - float(row['Lng1'])
                row['delta_lat'] = float(row['Lat2']) - float(row['Lat1'])
                self.allData[int(row['Time'])][row['strID_Tar']] = row
        
        self.vl_refObject = QgsVectorLayer("Point?crs=epsg:4326","refObject","memory")
        self.vl_targetObject = QgsVectorLayer("Point?crs=epsg:4326","targetObject","memory")
        self.vl_refObject.rendererV2().symbol().setSize(3.0);
        self.vl_targetObject.rendererV2().symbol().setSize(1.0);
        self.vl_refObject.rendererV2().symbol().setColor(QtGui.QColor('#ffff15'));
        self.vl_targetObject.rendererV2().symbol().setColor(QtGui.QColor('#fb01ff'));
        
        records = self.allData[0]
        
        pr_refObject = self.vl_refObject.dataProvider()
        pr_refObject.addAttributes([QgsField("RealTime", QVariant.String),
                                    QgsField("strID_Ref", QVariant.String),
                                    QgsField("strID_Tar", QVariant.String),
                                    QgsField("Dis", QVariant.String),
                                    QgsField("Ang", QVariant.String)])
        self.vl_refObject.updateFields()
        pr_refObject_features = []
        
        
        pr_targetObject = self.vl_targetObject.dataProvider()
        pr_targetObject.addAttributes([QgsField("RealTime", QVariant.String),
                                    QgsField("strID_Ref", QVariant.String),
                                    QgsField("strID_Tar", QVariant.String),
                                    QgsField("Dis", QVariant.String),
                                    QgsField("Ang", QVariant.String)])
        self.vl_targetObject.updateFields()
        pr_targetObject_features = []
        
        for key,record in records.iteritems() :
            pr_refObject_feature = QgsFeature()
            pr_refObject_feature.setAttributes([str(record['RealTime']),
                                                str(record['strID_Ref']),
                                                str(record['strID_Tar']),
                                                str(record['Dis']),
                                                str(record['Ang'])])
            pr_refObject_feature.setGeometry(
                QgsGeometry.fromPoint(
                    QgsPoint(float(record['Lng1']), float(record['Lat1']))))
            pr_refObject_features.append(pr_refObject_feature)
            
            pr_targetObject_feature = QgsFeature()
            pr_targetObject_feature.setAttributes([str(record['RealTime']),
                                                str(record['strID_Ref']),
                                                str(record['strID_Tar']),
                                                str(record['Dis']),
                                                str(record['Ang'])])
            pr_targetObject_feature.setGeometry(
                QgsGeometry.fromPoint(
                    QgsPoint(float(record['Lng2']), float(record['Lat2']))))
            pr_targetObject_features.append(pr_targetObject_feature)
            
            
        [res1, outFeats1] = pr_refObject.addFeatures(pr_refObject_features)
        if not res1:
                QMessageBox.information(self.iface.mainWindow(), 'Error',
                                    u"添加要素失败")
                return
        [res2, outFeats2] = pr_targetObject.addFeatures(pr_targetObject_features)
        if not res2:
                QMessageBox.information(self.iface.mainWindow(), 'Error',
                                    u"添加要素失败")
                return
        
        # 设置地图中心
        
        if not len(records.keys()) == 0:
            self.iface.mapCanvas().setCenter(
                        QgsPoint(float(records[records.keys()[0]]['Lng1']), 
                                 float(records[records.keys()[0]]['Lat1'])))
        
            
        if self.vl_refObject.isValid() and self.vl_targetObject.isValid():
            QgsMapLayerRegistry.instance().addMapLayer(self.vl_refObject)
            QgsMapLayerRegistry.instance().addMapLayer(self.vl_targetObject)
            
            self.vl = QgsVectorLayer("LineString?crs=epsg:4326","line", "memory")
            self.vl_trajectory = QgsVectorLayer("LineString?crs=epsg:4326","target_trajectory", "memory")
            
            self.traversedDataTime.append(0)
            
            pr = self.vl.dataProvider()
            features = []
            
            for key , record in records.iteritems():
                fet = QgsFeature()
                fet.setGeometry(QgsGeometry.fromPolyline([
                    QgsPoint(float(record['Lng1']), float(record['Lat1'])), 
                    QgsPoint(float(record['Lng2']), float(record['Lat2']))]))
                features.append(fet)
            [res, outFeats] = pr.addFeatures(features)
            
            if not res:
                QMessageBox.information(self.iface.mainWindow(), 'Error',
                                    u"添加要素失败")
                return
            
            QgsMapLayerRegistry.instance().addMapLayer(self.vl)
            QgsMapLayerRegistry.instance().addMapLayer(self.vl_trajectory)
            
            for key, record in records.iteritems():
                if not float(record['Dis']) == 0.0:
                    # 将数据显示到右侧表格中
                    self.showResultDockWidget.tableWidget.insertRow(
                        self.showResultDockWidget.tableWidget.rowCount())
                    r = self.showResultDockWidget.tableWidget.rowCount() - 1
                    self.showResultDockWidget.tableWidget.setItem(
                        r, 0, QTableWidgetItem(str(record['RealTime'])))
                    self.showResultDockWidget.tableWidget.setItem(
                        r, 1, QTableWidgetItem(str(record['strID_Ref'])))
                    self.showResultDockWidget.tableWidget.setItem(
                        r, 2, QTableWidgetItem(str(record['strID_Tar'])))
                    self.showResultDockWidget.tableWidget.setItem(
                        r, 3, QTableWidgetItem(str(record['Dis'])))
                    self.showResultDockWidget.tableWidget.setItem(
                        r, 4, QTableWidgetItem(str(record['Ang'])))
                 
        self.initMCTimeSlider()
        self.dock.horizontalTimeSlider.valueChanged.connect(self.mcTimeSliderChanged_obq)
        self.dock.pushButtonPlay.clicked.connect(self.autoPlay)
    
    # 时序改变
    '''动态obq时间变化调用'''    
    def mcTimeSliderChanged_obq(self, value = None):
#         try :
        if value == None:
            value = self.dock.horizontalTimeSlider.value() 
        
        if value == 0:
            self.traversedDataTime = []
        
        pr1 = self.vl_refObject.dataProvider()
        pr2 = self.vl_targetObject.dataProvider()
        pr = self.vl.dataProvider()
        pr_trajectory = self.vl_trajectory.dataProvider()
        
        # 删除原先图层
        pr1.deleteFeatures(self.vl_refObject.allFeatureIds())
        pr2.deleteFeatures(self.vl_targetObject.allFeatureIds())
        pr.deleteFeatures(self.vl.allFeatureIds())
        pr_trajectory.deleteFeatures(self.vl_trajectory.allFeatureIds())
        
        # 当前时间对应的记录
        currentRecord = self.allData[value]
        
        pr1_features = []
        pr2_features = []
        pr_trajectory_features = []
        for key , record in currentRecord.iteritems():
            pr1_feature = QgsFeature()
            pr1_feature.setAttributes([str(record['RealTime']),
                                    str(record['strID_Ref']),
                                    str(record['strID_Tar']),
                                    str(record['Dis']),
                                    str(record['Ang'])])
            pr1_feature.setGeometry(
                QgsGeometry.fromPoint(
                    QgsPoint(float(record['Lng1']), float(record['Lat1']))))
            pr1_features.append(pr1_feature)
            
            pr2_feature = QgsFeature()
            pr2_feature.setAttributes([str(record['RealTime']),
                                    str(record['strID_Ref']),
                                    str(record['strID_Tar']),
                                    str(record['Dis']),
                                    str(record['Ang'])])
            pr2_feature.setGeometry(
                QgsGeometry.fromPoint(
                    QgsPoint(float(record['Lng2']), float(record['Lat2']))))
            pr2_features.append(pr2_feature)
            
            
        if not value == 0:
            # 将target的轨迹进行连接
            for traversedTime in self.traversedDataTime:
                # 绘制目标点
                traversedTimeRecord = self.allData[traversedTime]
                
                for key, record in traversedTimeRecord.iteritems():
                    pr2_feature = QgsFeature()
                    pr2_feature.setAttributes([str(record['RealTime']),
                                            str(record['strID_Ref']),
                                            str(record['strID_Tar']),
                                            str(record['Dis']),
                                            str(record['Ang'])])
                    pr2_feature.setGeometry(
                        QgsGeometry.fromPoint(
                            QgsPoint(float(currentRecord[currentRecord.keys()[0]]['Lng1']) + record['delta_lng'], 
                                     float(currentRecord[currentRecord.keys()[0]]['Lat1']) + record['delta_lat'])))
                    pr2_features.append(pr2_feature)
                
                # 绘制目标点之间的连线
                if not traversedTime == 0:
                    previousTraversedTimeRecord = self.allData[traversedTime - 1]
                    
                    for key, record in previousTraversedTimeRecord.iteritems():
                        pr_trajectory_feature = QgsFeature()
                        pr_trajectory_feature.setGeometry(
                            QgsGeometry.fromPolyline([
                                    QgsPoint(float(currentRecord[currentRecord.keys()[0]]['Lng1']) + 
                                                traversedTimeRecord[key]['delta_lng'], 
                                             float(currentRecord[currentRecord.keys()[0]]['Lat1']) + 
                                                traversedTimeRecord[key]['delta_lat']), 
                                    QgsPoint(float(currentRecord[currentRecord.keys()[0]]['Lng1']) + 
                                                record['delta_lng'], 
                                             float(currentRecord[currentRecord.keys()[0]]['Lat1']) + 
                                                record['delta_lat'])
                                    ]))
                        pr_trajectory_features.append(pr_trajectory_feature)
            
            # 绘制当前目标点和前一个点之间的连线
            for key, record in traversedTimeRecord.iteritems():
                pr_trajectory_feature = QgsFeature()
                pr_trajectory_feature.setGeometry(
                    QgsGeometry.fromPolyline([
                        QgsPoint(float(currentRecord[currentRecord.keys()[0]]['Lng1']) + 
                                    traversedTimeRecord[key]['delta_lng'], 
                                 float(currentRecord[currentRecord.keys()[0]]['Lat1']) + 
                                    traversedTimeRecord[key]['delta_lat']), 
                        QgsPoint(float(currentRecord[key]['Lng2']), float(currentRecord[key]['Lat2']))
                        ]))
                pr_trajectory_features.append(pr_trajectory_feature)
            
        [res1, outFeats1] = pr1.addFeatures(pr1_features)
        [res2, outFeats2] = pr2.addFeatures(pr2_features)
        [trajectory_res, trajectory_outFeats] = pr_trajectory.addFeatures(pr_trajectory_features)
        
        pr_features = []
        for key , record in currentRecord.iteritems():
            pr_feature = QgsFeature()
            pr_feature.setGeometry(
                QgsGeometry.fromPolyline([
                        QgsPoint(float(record['Lng1']), float(record['Lat1'])), 
                        QgsPoint(float(record['Lng2']), float(record['Lat2']))]))
            pr_features.append(pr_feature)
        [res, outFeats] = pr.addFeatures(pr_features)
        
        self.traversedDataTime.append(value)
        
        # 设置地图中心
        if not len(currentRecord.keys()) == 0:
            self.iface.mapCanvas().setCenter(
                QgsPoint(float(currentRecord[currentRecord.keys()[0]]['Lng1']), 
                         float(currentRecord[currentRecord.keys()[0]]['Lat1'])))
        
        if not res or not res1 or not res2 or not trajectory_res:
            QMessageBox.information(self.iface.mainWindow(), 'Error',
                                u"添加要素失败")
            
        for key, record in currentRecord.iteritems():
            if not float(record['Dis']) == 0.0:
                # 将数据显示到右侧表格中
                self.showResultDockWidget.tableWidget.insertRow(
                    self.showResultDockWidget.tableWidget.rowCount())
                r = self.showResultDockWidget.tableWidget.rowCount() - 1
                self.showResultDockWidget.tableWidget.setItem(
                    r, 0, QTableWidgetItem(str(record['RealTime'])))
                self.showResultDockWidget.tableWidget.setItem(
                    r, 1, QTableWidgetItem(str(record['strID_Ref'])))
                self.showResultDockWidget.tableWidget.setItem(
                    r, 2, QTableWidgetItem(str(record['strID_Tar'])))
                self.showResultDockWidget.tableWidget.setItem(
                    r, 3, QTableWidgetItem(str(record['Dis'])))
                self.showResultDockWidget.tableWidget.setItem(
                    r, 4, QTableWidgetItem(str(record['Ang'])))
            
        self.iface.mapCanvas().refresh()
        self.vl_refObject.triggerRepaint()
        self.vl_targetObject.triggerRepaint()
        self.vl.triggerRepaint()
        self.vl_trajectory.triggerRepaint()
        self.iface.legendInterface().refreshLayerSymbology(self.vl_refObject)
        self.iface.legendInterface().refreshLayerSymbology(self.vl_targetObject)
        self.iface.legendInterface().refreshLayerSymbology(self.vl)
        self.iface.legendInterface().refreshLayerSymbology(self.vl_trajectory)
#         except Exception as e:
#             QMessageBox.information(self.iface.mainWindow(), 'Error',
#                                         u"操作失败")
#             self.qTimer.stop()
#             self.dock.horizontalTimeSlider.setValue(self.dock.horizontalTimeSlider.minimum())
            
    '''动态散点图'''
    def dynamicScatter(self, dataPath):
        # 读取C++代码生成的文件，并进行可视化
        filepath = dataPath + "_result.csv"
            
        # 读取csv文件中的所有数据，用dict进行存储
        self.allData = {}
        
        '''初始化allData字典，每个value是列表，保存对应时间的记录'''
        for time in range(0,55):
            self.allData[time] = []
        
        # 保存所有已经遍历过的时间点
        self.traversedDataTime = []
        with open(filepath) as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                self.allData[int(row['Time'])].append(row)
        
        self.vl_refObject = QgsVectorLayer("Point?crs=epsg:4326","refObject","memory")
        self.vl_targetObject = QgsVectorLayer("Point?crs=epsg:4326","targetObject","memory")
        self.vl_refObject.rendererV2().symbol().setSize(3.0);
        self.vl_targetObject.rendererV2().symbol().setSize(2.0);
        self.vl_refObject.rendererV2().symbol().setColor(QtGui.QColor('#ffff15'));
        self.vl_targetObject.rendererV2().symbol().setColor(QtGui.QColor('#fb01ff'));
        
        records = self.allData[0]
        
        if not len(records) == 0:
            pr_refObject = self.vl_refObject.dataProvider()
            pr_refObject_features = []
            pr_refObject.addAttributes([QgsField("RealTime", QVariant.String),
                                    QgsField("strID_Ref", QVariant.String),
                                    QgsField("strID_Tar", QVariant.String),
                                    QgsField("Speed", QVariant.Double),
                                    QgsField("Accelerat", QVariant.Double)])
            self.vl_refObject.updateFields()
        
            pr_targetObject = self.vl_targetObject.dataProvider()
            pr_targetObject_features = []
            pr_targetObject.addAttributes([QgsField("RealTime", QVariant.String),
                                    QgsField("strID_Ref", QVariant.String),
                                    QgsField("strID_Tar", QVariant.String),
                                    QgsField("Speed", QVariant.Double),
                                    QgsField("Accelerat", QVariant.Double)])
            self.vl_targetObject.updateFields()
        
            pr_refObject_feature = QgsFeature()
            if 'Speed' in records[0]:
                pr_refObject_feature.setAttributes([str(records[0]['RealTime']),
                                                str(records[0]['strID_Ref']),
                                                str(records[0]['strID_Tar']),
                                                float(records[0]['Speed']),
                                                float(records[0]['Accelerat'])])
            else:
                pr_refObject_feature.setAttributes([str(records[0]['RealTime']),
                                                str(records[0]['strID_Ref']),
                                                str(records[0]['strID_Tar']),
                                                0.0,
                                                0.0])
            pr_refObject_feature.setGeometry(
                QgsGeometry.fromPoint(
                    QgsPoint(float(records[0]['Lng1']), float(records[0]['Lat1']))))
            pr_refObject_features.append(pr_refObject_feature)
            [res1, outFeats1] = pr_refObject.addFeatures(pr_refObject_features)
        
            for record in records :
                pr_targetObject_feature = QgsFeature()
                
                if 'Speed' in record:
                    pr_targetObject_feature.setAttributes([str(record['RealTime']),
                                                    str(record['strID_Ref']),
                                                    str(record['strID_Tar']),
                                                    float(record['Speed']),
                                                    float(record['Accelerat'])])
                else:
                    pr_targetObject_feature.setAttributes([str(record['RealTime']),
                                                    str(record['strID_Ref']),
                                                    str(record['strID_Tar']),
                                                    0.0,
                                                    0.0])
                pr_targetObject_feature.setGeometry(
                    QgsGeometry.fromPoint(
                        QgsPoint(float(record['Lng2']), float(record['Lat2']))))
                pr_targetObject_features.append(pr_targetObject_feature)
                [res2, outFeats2] = pr_targetObject.addFeatures(pr_targetObject_features)
            if not res1:
                QMessageBox.information(self.iface.mainWindow(), 'Error',
                                    u"添加要素失败")
                return
        
            if not res2:
                QMessageBox.information(self.iface.mainWindow(), 'Error',
                                    u"添加要素失败")
                return
        
            # 设置地图中心
            self.iface.mapCanvas().setCenter(
                    QgsPoint(float(records[0]['Lng1']), 
                             float(records[0]['Lat1'])))
        
            '''根据目标点加速度的正负显示不同的颜色'''
            if 'Accelerat' in records[0]:
                # 渲染样式
                myRangeList = []
                
                # symbol 1
                myMin = 0
                myMax = 100
                myLabel = 'acc > 0'
                myColour = QtGui.QColor('#ff0105')
                mySymbol1 = QgsSymbolV2.defaultSymbol(self.vl_targetObject.geometryType())
                mySymbol1.setColor(myColour)
                myRange1 = QgsRendererRangeV2(myMin, myMax, mySymbol1, myLabel)
                myRangeList.append(myRange1)
                
                # symbol 1
                myMin = -100
                myMax = 0
                myLabel = 'acc < 0'
                myColour = QtGui.QColor('#01ff4d')
                mySymbol2 = QgsSymbolV2.defaultSymbol(self.vl_targetObject.geometryType())
                mySymbol2.setColor(myColour)
                myRange2 = QgsRendererRangeV2(myMin, myMax, mySymbol2, myLabel)
                myRangeList.append(myRange2)
                
                myRenderer = QgsGraduatedSymbolRendererV2('', myRangeList)
                myRenderer.setMode(QgsGraduatedSymbolRendererV2.EqualInterval)
                myRenderer.setClassAttribute('Accelerat')
                self.vl_targetObject.setRendererV2(myRenderer)
        if self.vl_refObject.isValid() and self.vl_targetObject.isValid():
            QgsMapLayerRegistry.instance().addMapLayer(self.vl_refObject)
            QgsMapLayerRegistry.instance().addMapLayer(self.vl_targetObject)
            
        if not len(records) == 0 and 'Speed' in records[0]:
            currentTime = records[0]['RealTime']
            closingNum = len(records)
            accelerateNum = 0
            decelerateNum = 0
            for record in records:
                
                if float(record['Accelerat']) < 0:
                    decelerateNum = decelerateNum + 1
                if float(record['Accelerat']) > 0:
                    accelerateNum = accelerateNum + 1
                
                if not float(record['Dis']) == 0.0:
                    # 将数据显示到右侧表格中
                    self.showResultDockWidget.tableWidget.insertRow(
                        self.showResultDockWidget.tableWidget.rowCount())
                    r = self.showResultDockWidget.tableWidget.rowCount() - 1
                    self.showResultDockWidget.tableWidget.setItem(
                        r, 0, QTableWidgetItem(str(record['RealTime'])))
                    self.showResultDockWidget.tableWidget.setItem(
                        r, 1, QTableWidgetItem(str(record['strID_Ref'])))
                    self.showResultDockWidget.tableWidget.setItem(
                        r, 2, QTableWidgetItem(str(record['strID_Tar'])))
                    self.showResultDockWidget.tableWidget.setItem(
                        r, 3, QTableWidgetItem(str(record['Dis'])))
                    self.showResultDockWidget.tableWidget.setItem(
                        r, 4, QTableWidgetItem(str(record['Ang'])))
            
            self.showResultDockWidget.currentTime.setText(currentTime)
            self.showResultDockWidget.closingNum.setText(str(closingNum))
            self.showResultDockWidget.accelerateNum.setText(str(accelerateNum))
            self.showResultDockWidget.decelerateNum.setText(str(decelerateNum))
            self.showResultDockWidget.currentTime.show()
            self.showResultDockWidget.closingNum.show()
            self.showResultDockWidget.accelerateNum.show()
            self.showResultDockWidget.decelerateNum.show()
            self.showResultDockWidget.label_2.show()
            self.showResultDockWidget.label_4.show()
            self.showResultDockWidget.label_8.show()
            self.showResultDockWidget.label_6.show()
        else:
            for record in records:
                if not float(record['Dis']) == 0.0:
                    # 将数据显示到右侧表格中
                    self.showResultDockWidget.tableWidget.insertRow(
                        self.showResultDockWidget.tableWidget.rowCount())
                    r = self.showResultDockWidget.tableWidget.rowCount() - 1
                    self.showResultDockWidget.tableWidget.setItem(
                        r, 0, QTableWidgetItem(str(record['RealTime'])))
                    self.showResultDockWidget.tableWidget.setItem(
                        r, 1, QTableWidgetItem(str(record['strID_Ref'])))
                    self.showResultDockWidget.tableWidget.setItem(
                        r, 2, QTableWidgetItem(str(record['strID_Tar'])))
                    self.showResultDockWidget.tableWidget.setItem(
                        r, 3, QTableWidgetItem(str(record['Dis'])))
                    self.showResultDockWidget.tableWidget.setItem(
                        r, 4, QTableWidgetItem(str(record['Ang'])))
                 
        self.initMCTimeSlider()
        self.dock.horizontalTimeSlider.valueChanged.connect(self.mcTimeSliderChanged_rbq)
        self.dock.pushButtonPlay.clicked.connect(self.autoPlay)
    
    def mcTimeSliderChanged_rbq(self, value=None):
#         try :
        if value == None:
            value = self.dock.horizontalTimeSlider.value() 
        
        pr1 = self.vl_refObject.dataProvider()
        pr2 = self.vl_targetObject.dataProvider()
        
        # 删除原先图层
        pr1.deleteFeatures(self.vl_refObject.allFeatureIds())
        pr2.deleteFeatures(self.vl_targetObject.allFeatureIds())
        
        # 当前时间对应的记录
        currentRecord = self.allData[value]
        
        if not len(currentRecord) == 0:
            pr1_features = []
            pr1_feature = QgsFeature()
            if 'Speed' in currentRecord[0]:
                pr1_feature.setAttributes([str(currentRecord[0]['RealTime']),
                                                str(currentRecord[0]['strID_Ref']),
                                                str(currentRecord[0]['strID_Tar']),
                                                float(currentRecord[0]['Speed']),
                                                float(currentRecord[0]['Accelerat'])])
            else:
                pr1_feature.setAttributes([str(currentRecord[0]['RealTime']),
                                                str(currentRecord[0]['strID_Ref']),
                                                str(currentRecord[0]['strID_Tar']),
                                                0.0,
                                                0.0])
            pr1_feature.setGeometry(
                QgsGeometry.fromPoint(
                    QgsPoint(float(currentRecord[0]['Lng1']), float(currentRecord[0]['Lat1']))))
            pr1_features.append(pr1_feature)
            pr2_features = []
            for record in currentRecord:
                pr2_feature = QgsFeature()
                if 'Speed' in record:
                    pr2_feature.setAttributes([str(record['RealTime']),
                                                str(record['strID_Ref']),
                                                str(record['strID_Tar']),
                                                float(record['Speed']),
                                                float(record['Accelerat'])])
                else:
                    pr2_feature.setAttributes([str(record['RealTime']),
                                                str(record['strID_Ref']),
                                                str(record['strID_Tar']),
                                                0.0,
                                                0.0])
                pr2_feature.setGeometry(
                    QgsGeometry.fromPoint(
                        QgsPoint(float(record['Lng2']), float(record['Lat2']))))
                pr2_features.append(pr2_feature)
            
            [res1, outFeats1] = pr1.addFeatures(pr1_features)
            [res2, outFeats2] = pr2.addFeatures(pr2_features)
    
        
            # 设置地图中心
            self.iface.mapCanvas().setCenter(
                QgsPoint(float(currentRecord[0]['Lng1']), float(currentRecord[0]['Lat1'])))
        
            if not res1 or not res2:
                QMessageBox.information(self.iface.mainWindow(), 'Error',
                                u"添加要素失败")
            
            if 'Speed' in currentRecord[0]:
                currentTime = currentRecord[0]['RealTime']
                closingNum = len(currentRecord)
                accelerateNum = 0
                decelerateNum = 0
                for record in currentRecord:
                    
                    if float(record['Accelerat']) < 0:
                        decelerateNum = decelerateNum + 1
                    if float(record['Accelerat']) > 0:
                        accelerateNum = accelerateNum + 1
                    
                    if not float(record['Dis']) == 0.0:
                        # 将数据显示到右侧表格中
                        self.showResultDockWidget.tableWidget.insertRow(
                            self.showResultDockWidget.tableWidget.rowCount())
                        r = self.showResultDockWidget.tableWidget.rowCount() - 1
                        self.showResultDockWidget.tableWidget.setItem(
                            r, 0, QTableWidgetItem(str(record['RealTime'])))
                        self.showResultDockWidget.tableWidget.setItem(
                            r, 1, QTableWidgetItem(str(record['strID_Ref'])))
                        self.showResultDockWidget.tableWidget.setItem(
                            r, 2, QTableWidgetItem(str(record['strID_Tar'])))
                        self.showResultDockWidget.tableWidget.setItem(
                            r, 3, QTableWidgetItem(str(record['Dis'])))
                        self.showResultDockWidget.tableWidget.setItem(
                            r, 4, QTableWidgetItem(str(record['Ang'])))
                
                self.showResultDockWidget.currentTime.setText(currentTime)
                self.showResultDockWidget.closingNum.setText(str(closingNum))
                self.showResultDockWidget.accelerateNum.setText(str(accelerateNum))
                self.showResultDockWidget.decelerateNum.setText(str(decelerateNum))
            else:
                for record in currentRecord:
                    if not float(record['Dis']) == 0.0:
                        # 将数据显示到右侧表格中
                        self.showResultDockWidget.tableWidget.insertRow(
                            self.showResultDockWidget.tableWidget.rowCount())
                        r = self.showResultDockWidget.tableWidget.rowCount() - 1
                        self.showResultDockWidget.tableWidget.setItem(
                            r, 0, QTableWidgetItem(str(record['RealTime'])))
                        self.showResultDockWidget.tableWidget.setItem(
                            r, 1, QTableWidgetItem(str(record['strID_Ref'])))
                        self.showResultDockWidget.tableWidget.setItem(
                            r, 2, QTableWidgetItem(str(record['strID_Tar'])))
                        self.showResultDockWidget.tableWidget.setItem(
                            r, 3, QTableWidgetItem(str(record['Dis'])))
                        self.showResultDockWidget.tableWidget.setItem(
                            r, 4, QTableWidgetItem(str(record['Ang'])))
            
        self.iface.mapCanvas().refresh()
        self.vl_refObject.triggerRepaint()
        self.vl_targetObject.triggerRepaint()
        self.iface.legendInterface().refreshLayerSymbology(self.vl_refObject)
        self.iface.legendInterface().refreshLayerSymbology(self.vl_targetObject)
#         except Exception as e:
#             QMessageBox.information(self.iface.mainWindow(), 'Error',
#                                         u"操作失败")
#             self.qTimer.stop()
#             self.dock.horizontalTimeSlider.setValue(self.dock.horizontalTimeSlider.minimum())
    
    def visualData_pq(self,pq_dataPath, pq_refObject, pq_max_distance, 
                               pq_min_distance, pq_max_angle,pq_min_angle,function):
        if function == 'Intimate Contact':
            # 设置python调用c++代码
            self.dll.GetIntimateContactObjectsFromCube.argtypes = [c_char_p,c_char_p,c_char_p]
            self.dll.GetIntimateContactObjectsFromCube.restype = c_void_p
            dis = 'dis < ' + str(pq_max_distance)
            self.dll.GetIntimateContactObjectsFromCube(pq_dataPath,pq_refObject,dis)
            
            self.dynamicScatter(pq_dataPath)
        elif function == 'Closer Object':
            # 设置python调用c++代码
            self.dll.GetCloserByTime2.argtypes = [c_char_p,c_char_p]
            self.dll.GetCloserByTime2.restype = c_void_p
            self.dll.GetCloserByTime2(pq_dataPath,pq_refObject)
            
            self.dynamicScatter(pq_dataPath)
        elif function == 'Follower':
            # 设置python调用c++代码
            self.dll.GetFollowers.argtypes = [c_char_p,c_char_p,c_double,c_double,c_double,c_double]
            self.dll.GetFollowers.restype = c_void_p
            self.dll.GetFollowers(pq_dataPath,pq_refObject,
                                  pq_max_distance,pq_min_distance,pq_max_angle,pq_min_angle)
            
            self.dynamicVisual_obq(pq_dataPath)
        elif function == 'Trend Recognition':
            # 设置python调用c++代码
            self.dll.GetObjectTrendWithMe.argtypes = [c_char_p,c_char_p,c_int]
            self.dll.GetObjectTrendWithMe.restype = c_void_p
#             self.dll.GetObjectTrendWithMe(dataPath,refObject)
            
#             self.staticVisual_obq(dataPath, refObject, targetObject, time)
    
    def visualDataWithoutTargetObject(self, dataPath, refObject, time):
        self.dll.TargetDrilling.argtypes = [c_char_p,c_char_p,c_int]
        self.dll.TargetDrilling.restype = c_void_p
        self.dll.TargetDrilling(dataPath,refObject,time)
        
        # 读取C++代码生成的文件，并进行可视化
        filepath = dataPath + "_result.csv"
        
        # 添加图层
        uri1 = "file:///" + filepath + "?delimiter=%s&crs=epsg:4326&xField=%s&yField=%s" % (",", "Lng1", "Lat1")
        uri2 = "file:///" + filepath + "?delimiter=%s&crs=epsg:4326&xField=%s&yField=%s" % (",", "Lng2", "Lat2")
        self.vl_refObject = QgsVectorLayer(uri1, "refObject", "delimitedtext")
        self.vl_targetObject = QgsVectorLayer(uri2, "targetObject", "delimitedtext")
        self.vl_refObject.rendererV2().symbol().setSize(3.0);
        self.vl_targetObject.rendererV2().symbol().setSize(1.0);
        self.vl_refObject.rendererV2().symbol().setColor(QtGui.QColor('#ffff15'));
        self.vl_targetObject.rendererV2().symbol().setColor(QtGui.QColor('#fb01ff'));
        if self.vl_refObject.isValid() and self.vl_targetObject.isValid():
            QgsMapLayerRegistry.instance().addMapLayer(self.vl_refObject)
            QgsMapLayerRegistry.instance().addMapLayer(self.vl_targetObject)
            
            self.vl = QgsVectorLayer("LineString?crs=epsg:4326","line", "memory")
            pr = self.vl.dataProvider()
            features = []
            
            with open(filepath) as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    fet = QgsFeature()
                    fet.setGeometry(QgsGeometry.fromPolyline([
                        QgsPoint(float(row['Lng1']), float(row['Lat1'])), 
                        QgsPoint(float(row['Lng2']), float(row['Lat2']))]))
                    features.append(fet)
                    
                    if not float(row['Dis']) == 0.0:
                        # 将数据显示到右侧表格中
                        self.showResultDockWidget.tableWidget.insertRow(
                            self.showResultDockWidget.tableWidget.rowCount())
                        r = self.showResultDockWidget.tableWidget.rowCount() - 1
                        self.showResultDockWidget.tableWidget.setItem(
                            r, 0, QTableWidgetItem(str(row['RealTime'])))
                        self.showResultDockWidget.tableWidget.setItem(
                            r, 1, QTableWidgetItem(str(row['strID_Ref'])))
                        self.showResultDockWidget.tableWidget.setItem(
                            r, 2, QTableWidgetItem(str(row['strID_Tar'])))
                        self.showResultDockWidget.tableWidget.setItem(
                            r, 3, QTableWidgetItem(str(row['Dis'])))
                        self.showResultDockWidget.tableWidget.setItem(
                            r, 4, QTableWidgetItem(str(row['Ang'])))
                
                
            [res, outFeats] = pr.addFeatures(features)
            
            if not res:
                QMessageBox.information(self.iface.mainWindow(), 'Error',
                                    u"添加要素失败")
            #self.iface.mapCanvas().refresh()
            QgsMapLayerRegistry.instance().addMapLayer(self.vl)
        else:
            QMessageBox.information(self.iface.mainWindow(), 'Error', u'图层加载失败')
            return
    
    def visualData(self, dataPath, refObject, targetObject):
        self.dll.TimeDrilling.argtypes=[c_char_p, c_char_p, c_char_p]
        self.dll.TimeDrilling.restype=c_void_p
        self.dll.TimeDrilling(dataPath,refObject,targetObject)
        
        # 读取C++代码生成的文件，并进行可视化
        filepath = dataPath + "_result.csv"
            
        # 读取csv文件中的所有数据，用dict进行存储
        self.allData = {}
        
        # 保存所有已经遍历过的时间点
        self.traversedDataTime = []
        
        with open(filepath) as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                # 计算每时刻目标点和参照点的坐标差值，以方便显示相对位置
                row['delta_lng'] = float(row['Lng2']) - float(row['Lng1'])
                row['delta_lat'] = float(row['Lat2']) - float(row['Lat1'])
                self.allData[int(row['Time'])] = row
        
        self.vl_refObject = QgsVectorLayer("Point?crs=epsg:4326","refObject","memory")
        self.vl_targetObject = QgsVectorLayer("Point?crs=epsg:4326","targetObject","memory")
        self.vl_refObject.rendererV2().symbol().setSize(3.0);
        self.vl_targetObject.rendererV2().symbol().setSize(1.0);
        self.vl_refObject.rendererV2().symbol().setColor(QtGui.QColor('#ffff15'));
        self.vl_targetObject.rendererV2().symbol().setColor(QtGui.QColor('#fb01ff'));
        
        record1 = self.allData[0]
        pr_refObject = self.vl_refObject.dataProvider()
        pr_refObject_feature = QgsFeature()
        pr_refObject_feature.setGeometry(
            QgsGeometry.fromPoint(
                QgsPoint(float(record1['Lng1']), float(record1['Lat1']))))
        [res1, outFeats1] = pr_refObject.addFeatures([pr_refObject_feature])
        if not res1:
                QMessageBox.information(self.iface.mainWindow(), 'Error',
                                    u"添加要素失败")
                return
        
        # 设置地图中心
        self.iface.mapCanvas().setCenter(
                    QgsPoint(float(record1['Lng1']), float(record1['Lat1'])))
        
        pr_targetObject = self.vl_targetObject.dataProvider()
        pr_targetObject_feature = QgsFeature()
        pr_targetObject_feature.setGeometry(
            QgsGeometry.fromPoint(
                QgsPoint(float(record1['Lng2']), float(record1['Lat2']))))
        [res2, outFeats2] = pr_targetObject.addFeatures([pr_targetObject_feature])
        if not res2:
                QMessageBox.information(self.iface.mainWindow(), 'Error',
                                    u"添加要素失败")
                return
        
        if self.vl_refObject.isValid() and self.vl_targetObject.isValid():
            QgsMapLayerRegistry.instance().addMapLayer(self.vl_refObject)
            QgsMapLayerRegistry.instance().addMapLayer(self.vl_targetObject)
            
            self.vl = QgsVectorLayer("LineString?crs=epsg:4326","line", "memory")
            self.vl_trajectory = QgsVectorLayer("LineString?crs=epsg:4326","target_trajectory", "memory")
            
            self.traversedDataTime.append(0)
            
            pr = self.vl.dataProvider()
            features = []
            
            fet = QgsFeature()
            fet.setGeometry(QgsGeometry.fromPolyline([
                QgsPoint(float(record1['Lng1']), float(record1['Lat1'])), 
                QgsPoint(float(record1['Lng2']), float(record1['Lat2']))]))
            features.append(fet)
            [res, outFeats] = pr.addFeatures(features)
            
            if not res:
                QMessageBox.information(self.iface.mainWindow(), 'Error',
                                    u"添加要素失败")
                return
            
            QgsMapLayerRegistry.instance().addMapLayer(self.vl)
            QgsMapLayerRegistry.instance().addMapLayer(self.vl_trajectory)
            
            if not float(record1['Dis']) == 0.0:
                # 将数据显示到右侧表格中
                self.showResultDockWidget.tableWidget.insertRow(
                    self.showResultDockWidget.tableWidget.rowCount())
                r = self.showResultDockWidget.tableWidget.rowCount() - 1
                self.showResultDockWidget.tableWidget.setItem(
                    r, 0, QTableWidgetItem(str(record1['RealTime'])))
                self.showResultDockWidget.tableWidget.setItem(
                    r, 1, QTableWidgetItem(str(record1['strID_Ref'])))
                self.showResultDockWidget.tableWidget.setItem(
                    r, 2, QTableWidgetItem(str(record1['strID_Tar'])))
                self.showResultDockWidget.tableWidget.setItem(
                    r, 3, QTableWidgetItem(str(record1['Dis'])))
                self.showResultDockWidget.tableWidget.setItem(
                    r, 4, QTableWidgetItem(str(record1['Ang'])))
            
        
        self.initMCTimeSlider()
        self.dock.horizontalTimeSlider.valueChanged.connect(self.mcTimeSliderChanged)
        self.dock.pushButtonPlay.clicked.connect(self.autoPlay)
                
    def initMCTimeSlider(self):
        max = self.filesNum - 1
        min = 0
        step = 1
        self.dock.labelStartTime.setText(str(min))
        self.dock.labelEndTime.setText(str(max))
        self.dock.horizontalTimeSlider.setMinimum(min)
        self.dock.horizontalTimeSlider.setMaximum(max)
        self.dock.horizontalTimeSlider.setSingleStep(step)
        self.dock.horizontalTimeSlider.setValue(self.dock.horizontalTimeSlider.minimum())
        
        # 定时器
        self.qTimer = QTimer(self)
        self.qTimer.timeout.connect(self.incrementValue)    
    
    def showTrajectory(self, trajectory_dataPath):
        files = os.listdir(trajectory_dataPath)
        for file in files:
            if not os.path.isdir(file) and '.txt' in file and not file.startswith('.') :
                self.tra_point = QgsVectorLayer("Point?crs=epsg:4326",os.path.splitext(file)[0],"memory")
                self.tra_line = QgsVectorLayer("LineString?crs=epsg:4326",os.path.splitext(file)[0], "memory")
                point_pr = self.tra_point.dataProvider()
                line_pr = self.tra_line.dataProvider()
                
                point_features = []
                line_features = []
                
                previous_row = None
                
                with open(trajectory_dataPath + "\\"+ file) as csvfile:
                    reader = csv.DictReader(csvfile)
                    for row in reader:
                        
                        point_feature = QgsFeature()
                        point_feature.setGeometry(
                            QgsGeometry.fromPoint(
                                QgsPoint(float(row['lng']), float(row['lat']))))
                        point_features.append(point_feature)
                        
                        if not previous_row == None:
                            line_feature = QgsFeature()
                            line_feature.setGeometry(QgsGeometry.fromPolyline([
                                QgsPoint(float(previous_row['lng']), float(previous_row['lat'])), 
                                QgsPoint(float(row['lng']), float(row['lat']))]))
                            line_features.append(line_feature)
                    
                        previous_row = row
                    
                [point_res, point_outFeats] = point_pr.addFeatures(point_features)
                [line_res, line_outFeats] = line_pr.addFeatures(line_features)
                
                if not point_res:
                    QMessageBox.information(self.iface.mainWindow(), 'Error',
                                        u"添加要素失败")
                    return
                if not line_res:
                    QMessageBox.information(self.iface.mainWindow(), 'Error',
                                        u"添加要素失败")
                    return
                
                QgsMapLayerRegistry.instance().addMapLayer(self.tra_point)
                QgsMapLayerRegistry.instance().addMapLayer(self.tra_line)