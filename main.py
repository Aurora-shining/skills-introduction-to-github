import glob
import os
import json
import base64
import re
import time
import traceback
import keyboard

from PyQt5.QtCore import QPoint, QSize
from PyQt5.QtGui import QPixmap, QIcon, QCursor
from wisdom_store.global_variable import IMAGE_SUFFIX_LIST
from wisdom_store.src.utils.image_transform import *

from wisdom_store.src.utils.label_coventor import LabelConventor
from wisdom_store.ui.main.UI_Main import Ui_Main
import wisdom_store.ui.main.resources_rc
from wisdom_store.ui.main.main_StyleSheet import *
from wisdom_store.ui.main.UI_Label import *
from wisdom_store.ui.main.UI_FileItem import Ui_FileItem
# from wisdom_store.wins.WidgetWinCustom import CalculationThread, CommonThread, WidgetWinCustom
from wisdom_store.wins import *
from wisdom_store.wins.component_keeplabel_conflict import KeepLabelConflictDialog
from wisdom_store.wins.main_BCA import BCASideBar
from wisdom_store.wins.main_delete_type import DeleteTypeWin
from wisdom_store.wins.main_filter import FilterWin
from wisdom_store.wins.main_foldingbar_item import FoldingBarItem
from wisdom_store.auth import Auth
from wisdom_store.config import Config
from wisdom_store.src.sdk.project.project import Project
from wisdom_store.wins.component_no_permission import checkPermission
import logging
import shutil
from PIL import ImageQt, Image
from wisdom_store.ui.main.UI_MainGraphicsView import MainGraphicsView
from wisdom_store.ui.main.UI_BirdView import BirdViewContainer
from wisdom_store.utils import getCurrentDateTime, setTimer, WindowsInhibitor, open_url_by_browser, openFolder
from wisdom_store.enums import ConflictMode
from wisdom_store.src.utils.base64translator import *
from wisdom_store.wins.component_import_conflict import ImportConflictDialog
import random
from wisdom_store.wins.component_alert_message import *
from tqdm import tqdm
from wisdom_store.src.api.user import user
from wisdom_store.wins.component_waiting import WaitingWin
from wisdom_store.wins.main_histogram_adjustment import HistogramChart
from wisdom_store.wins.main_image_rotation import ImageRotationWin
from wisdom_store.wins.start_about import AboutWin
from wisdom_store.wins.main_calculate_handle import CalculateWin
from wisdom_store.src.utils.image_process import *
from wisdom_store.wins.main_change_type import ChangeType
from wisdom_store.src.utils.image_resize import sliding_window_crop, resize_image

#1修改 引入标注展示和形态学变换两个文件
from wisdom_store.wins.main_labelshow import LabelShow
from wisdom_store.wins.main_morphology import Morphology

# 未使用
class paintTool():
    Rect = 0
    Polygon = 1
    Line = 2
    Scraw = 3

# 鼠标放大镜模式枚举。为0时鼠标不具有放大缩小功能；为1时具有缩小功能；为2时具有放大功能。
class zoomMode():
    NoZoom = 0
    ZoomIn = 1
    ZoomOut = 2

# 标注工具种类中文字典
labelClassDict = {
    'Circle': '圆',
    'Tag': '标签',
    'Point': '点',
    'Line': '线',
    'PolygonCurve': '多边形',
    'Rectangle': '矩形',
    'Scraw': '涂鸦',
    'Feedback': '反馈点',
    'MouseHoverScraw': '鼠标悬浮结果'
}

# 标注Windows控件
class MainWin(QMainWindow, WidgetWinCustom):
    signalRefreshProject = pyqtSignal(int)  # int表示当前选择的图像索引，刷新后重新选中改图像
    signal2 = pyqtSignal()
    signalBackHome = pyqtSignal()

    def __init__(self, config: Config, auth: Auth, project: Project = None):
        super(MainWin, self).__init__()
        self.total = 0
        self.current_num = 0
        self.config = config    # 配置文件
        self.auth = auth    # 用户名
        self.project = project  # 项目数据
        timeStarted = time.time()
        self.inhibitor: WindowsInhibitor = None

        self.fileList = []  # 文件路径列表  # views/main的loadProject方法会设置文件列表
        self.fileNameList = []  # 文件名列表
        self.lastFileIndex = -1  # 当前文件索引（当点击其他图片时，根据此索引保存标注，之后更新此索引）

        self.flagStatisticAnalyseWin = False

        #初始化空数组以存储选中的标签
        self.selected_labels = []
        self.selected_indexes = []
        self.current_row = None
        self.ChangeTypeDialog = None

        # 初始化窗口
        self.ui = Ui_Main()
        self.ui.setupUi(self)
        self.resize(1200, 750)
        self.ui.tabWidget.tabBar().setVisible(False)
        # self.ui.pageLabelBrief.setMaximumWidth(31)
        # 给combobox加上view，不加不能正常显示combobox样式
        # self.ui.comboBox_Sort.setView(QListView())
        self.ui.labelPartition.setText('当前类型')


        self.set_min_button(self.ui.tBtnMin)
        self.set_max_button(self.ui.tBtnMax)
        self.set_close_button(self.ui.tBtnClose)
        self.set_titleHeight(self.ui.frameTitle.height())
        self.set_comboBoxView()

        # 设置滚动条样式
        self.set_style_vScrollBar(self.ui.listwidgetFile.verticalScrollBar())
        self.set_style_vScrollBar(self.ui.tableWidget.verticalScrollBar())
        self.set_style_vScrollBar(self.ui.tableWidgetTargetList.verticalScrollBar())

        # 设置表格样式
        self.ui.tableWidget.setSelectionMode(QTableWidget.ExtendedSelection)
        self.ui.tableWidget.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.ui.tableWidgetTargetList.setSelectionMode(QTableWidget.ExtendedSelection)
        self.ui.tableWidgetTargetList.setSelectionBehavior(QAbstractItemView.SelectRows)

        # 进度条
        self.calculateWin = CalculateWin()
        self.calculateWin.setWindowModality(Qt.WindowModality.ApplicationModal)

        # 图像视图层
        layCentralWidget = QHBoxLayout()
        self.MainGraphicsView = MainGraphicsView(self.ui.frameCentral,self.config,self.project,self)
        self.set_style_vScrollBar(self.MainGraphicsView.verticalScrollBar())
        self.set_style_vScrollBar(self.MainGraphicsView.horizontalScrollBar())
        # self.ui.frameCentral=self.MainGraphicsView
        sizePolicy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.MainGraphicsView.sizePolicy().hasHeightForWidth())
        QApplication.processEvents()  # 刷新页面
        self.MainGraphicsView.setSizePolicy(sizePolicy)
        self.MainGraphicsView.setStyleSheet("")
        self.MainGraphicsView.setFrameShape(QFrame.StyledPanel)
        self.MainGraphicsView.setFrameShadow(QFrame.Raised)
        self.MainGraphicsView.setObjectName("MainGraphicsView")
        layCentralWidget.addWidget(self.MainGraphicsView)
        # self.ui.horizontalLayout.addWidget(self.MainGraphicsView)
        self.birdView = BirdViewContainer(self.ui.frameCentral, self.MainGraphicsView)
        self.birdView.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.birdView.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.ui.frameCentral.setLayout(layCentralWidget)
        QApplication.processEvents()  # 刷新页面

        # 动态创建菜单
        self.createMenus()

        # 初始化组件状态
        self.initComponent()
        self.ui.tabWidget.setCurrentIndex(0)

        self.ManipulationState = True
        self.StatisticsState = False
        self.transWidgetStatistics(False, 0)
        self.transWidgetManipulation(False)
        self.transWidgetEnhancement()

        self.ui.frameMenuBar.setMinimumHeight(40)

        # 侧边栏
        self.foldingWins = []
        self.ui.verticalLayout_enhancement.setAlignment(Qt.AlignTop)
        self.brightnessContrastAdjustmentWin = BCASideBar(self)
        self.ui.verticalLayout_enhancement.addWidget(self.brightnessContrastAdjustmentWin)
        self.foldingWins.append(self.brightnessContrastAdjustmentWin)

        self.histogramAdjustmentWin = HistogramChart(self)
        self.ui.verticalLayout_enhancement.addWidget(self.histogramAdjustmentWin)
        self.foldingWins.append(self.histogramAdjustmentWin)

        self.ui.verticalLayout_segmentation.setAlignment(Qt.AlignTop)
        self.thresholdSegmentationWin = ThresholdWindow(self.project, self.MainGraphicsView, self)
        self.thresholdSegmentationWin.singleAddLabelNum.connect(self.addLabelNum)
        self.thresholdSegmentationWin.segFalse.connect(lambda: alertError(self, "错误", "自动二值分割只支持包括背景类的两个类别", "Error Occurred!"))
        self.ui.verticalLayout_segmentation.addWidget(self.thresholdSegmentationWin)
        self.foldingWins.append(self.thresholdSegmentationWin)

        # 预分割缓存
        self.preSegCache = {}

        #1修改（增加标注后处理之下的两个小窗口，标注展示和形态学变换，仿照原图增强窗口来）
        self.ui.verticalLayout_processing.setAlignment(Qt.AlignTop)
        self.labelShowWin = LabelShow(self) #标注展示窗口1
        self.ui.verticalLayout_processing.addWidget(self.labelShowWin)
        self.foldingWins.append(self.labelShowWin)

        self.morphologyWin = Morphology(self) #形态学变换窗口2
        self.ui.verticalLayout_processing.addWidget(self.morphologyWin)
        self.foldingWins.append(self.morphologyWin)


        # 弹窗
        self.importPictureAndLabelWin = ImportWindow()
        self.edgeDetectionWin = EdgeDetection()
        self.equalizationWin = EqualizationWindow()
        self.exportWin = ExportWindow()
        QApplication.processEvents()  # 刷新页面
        self.setRulerWin: SetRuler = None
        self.setRulerSingleImageWin: SetRulerSingleImage = None
        self.statisticAnalyseWin: StatisticAnalyseWin = None

        self.regionDivideWin = RegionDivideWin()
        self.setPartitionTagWin: SetPartitionTag = None
        self.tagShowWin = TagShowWin(self)

        self.toolBoxSettingWin: ToolBoxSettingWindow = None
        self.loginWin = UserLoginWin()
        self.authWin = AuthorizationWin(self.auth)

        self.importPictureAndLabelWin.ui.tBtnClose.clicked.connect(
            lambda: self.hideSubWinAndShowMain(self.importPictureAndLabelWin))
        self.importPictureAndLabelWin.signalAutoSearch.connect(self.AutoSearch)
        self.importPictureAndLabelWin.signalDIYRule.connect(self.DIYRule)

        self.edgeDetectionWin.ui.pBtnClose.clicked.connect(lambda: self.hideSubWinAndShowMain(self.edgeDetectionWin))
        self.equalizationWin.ui.tBtnClose.clicked.connect(lambda: self.hideSubWinAndShowMain(self.equalizationWin))
        self.exportWin.ui.tBtnClose.clicked.connect(lambda: self.hideSubWinAndShowMain(self.exportWin))
        self.exportWin.signalExport.connect(self.Export)
        self.regionDivideWin.ui.pBtnClose.clicked.connect(lambda: self.hideSubWinAndShowMain(self.regionDivideWin))
        # self.statisticAnalyseWin.ui.pBtnClose.clicked.connect(
        #     lambda: self.hideSubWinAndShowMain(self.statisticAnalyseWin))
        # self.statisticAnalyseWin.ui.pBtnClose.clicked.connect(
        #     lambda: self.hideSubWinAndShowMain(self.statisticAnalyseWin))

        self.tagShowWin.ui.pBtnClose.clicked.connect(lambda: self.hideSubWinAndShowMain(self.tagShowWin))
        # self.thresholdSegmentationWin.ui.tBtnClose.clicked.connect(
        #     lambda: self.hideSubWinAndShowMain(self.thresholdSegmentationWin))

        self.loginWin.signalLoginSuccess.connect(self.showMainAndSetUserInfo)
        self.loginWin.ui.pBtnClose.clicked.connect(self.show)

        self.authWin.ui.pBtnClose.clicked.connect(self.show)
        self.ui.checkBoxSelectAll.clicked.connect(self.changeAllShowHide)
        self.ui.checkBoxSelectAll_2.clicked.connect(self.changeAllShowHideTarget)

        self.ui.tableWidget.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.ui.tableWidget.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.ui.tableWidgetTargetList.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.ui.tableWidgetTargetList.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.ui.checkBoxSelectAll.setChecked(True)
        self.ui.checkBoxSelectAll_2.setChecked(True)
        print(f'时间8：{(time.time() - timeStarted):.2f}s')
        # 信号与槽绑定
        self.signalConnect()

        # 推理时标注冲突的临时数据
        self.conflictResult = []
        # 导入时标注冲突的临时数据
        self.conflictImportResult = []
        self.conflictFileNameList = []

        # 生成右键菜单
        # self.createRightMenuMain()
        self.createRightMenuLabelTable()

        self.ui.tBtnHand.click()
        # 使鸟瞰图有效
        self.slotTBtnHand()

        # 隐藏未实现的控件
        # self.ui.horizontalSliderSensibility.setVisible(False)
        # self.ui.labelSensibility.setVisible(False)
        # self.ui.labelSensibilityValue.setVisible(False)
        self.ui.tBtnTag.setVisible(False)
        self.ui.tBtnSplit.setVisible(False)
        self.ui.tBtnMagnet.setVisible(False)
        self.ui.tBtnImageSegmentation.setVisible(False)
        self.ui.tBtnAIAnalysis.setVisible(False)
        self.ui.tBtnEdgeDetection.setVisible(False)
        self.ui.tBtnQuickLabel.setVisible(False)
        self.ui.widgetColor.setVisible(False)
        # self.ui.pushButtonSegmentation.setVisible(False)
        self.ui.toolButtonLog.setVisible(False)
        self.ui.pushButtonSort.setVisible(False)
        self.ui.pBtnLogin.setVisible(False)
        self.ui.labelAvatar.setVisible(False)
        self.actionImgCrop.setVisible(False)
        print(f'时间9：{(time.time() - timeStarted):.2f}s')

        self.setTypeSideBar()
        self.setTargetSideBar()
        #self.updateButtonIcon()

    def getToolObjByName(self, name):
        '''
        根据工具名获取ui对象
        '''
        if name == '手势拖动':
            return self.ui.tBtnHand
        elif name == '编辑标注':#A修改（修改了文字）
            return self.ui.tBtnArrow
        elif name == '放大镜':
            return self.ui.tBtnZoom
        elif name == '矩形标注':
            return self.ui.tBtnRectangleLabel
        elif name == '多边形标注':
            return self.ui.tBtnPolygonLabel
        elif name == '画刷':
            return self.ui.tBtnBrush
        elif name == '图像分割':
            return self.ui.tBtnSplit
        elif name == '点标注':
            return self.ui.tBtnPointLabel
        elif name == '标签标注':
            return self.ui.tBtnTag
        elif name == '直线标注':
            return self.ui.tBtnLine
        elif name == '圆形标注':
            return self.ui.tBtnCircle
        elif name == '魔术棒':
            return self.ui.tBtnAIMagic
        # elif name == '画框式标注':
        #     return self.ui.tBtnGrabcut
        elif name == '快捷标注':
            return self.ui.tBtnQuickLabel
        elif name == '智能分析':
            return self.ui.tBtnAIAnalysis
        elif name == '统计分析':
            return self.ui.tBtnStatisticalAnalysis
        elif name == '边缘检测':
            return self.ui.tBtnEdgeDetection
        elif name == '图像分割':
            return self.ui.tBtnImageSegmentation
        elif name == '磁性套索':
            return self.ui.tBtnMagnet
        else:
            return None

    def updateDateTime(self):
        try:
            self.ui.labelStatusITime.setText(getCurrentDateTime())
        except:
            self.timerThread = None

    def initComponent(self):
        '''
        初始化控件状态
        :return:pip install PyQt5
        '''
        # 隐藏一些组件
        self.ui.pBtnUserOp.hide()
        self.ui.pBtnLogin.hide()
        self.ui.labelAvatar.hide()
        self.ui.widgetThreshold.setVisible(False)
        self.state_scrollAreaPreview_hide = False
        # self.ui.widgetSensibility.setVisible(False)
        self.ui.widgetBrushSize.setVisible(False)
        self.ui.widgetZoom.setVisible(False)
        self.updateTopBarLabel()
        self.updateTopBarColor()
        zoomValue = 25
        zoomValueList = []
        while zoomValue <= 500:
            zoomValueStr = str(zoomValue) + '%'
            zoomValueList.append(zoomValueStr)
            zoomValue += 25
        self.ui.comboBoxZoomValue.clear()
        self.ui.comboBoxZoomValue.addItems(zoomValueList)
        # 根据配置更新工具栏
        self.refreshTools()

        # 隐藏日志窗口
        # self.ui.toolButtonLog.hide()
        # 标注对象表格存储索引
        self.targetListShow = []

        # 标注剪贴板
        self.labelKeepboard = []

        # 分页
        self.currentPage = 1
        self.pageSize = 20
        self.totalPage = math.ceil(len(self.project.importFiles) / self.pageSize)
        self.useThumbnail = True
        self.ui.widgetListTitle.setVisible(False)
        self.ui.comboBoxPage.setCurrentIndex(2)
        #给combobox加上view，不加不能正常显示combobox样式
        self.ui.comboBoxPage.setView(QListView())
        self.ui.comboBoxPage.view().model().item(0).setTextAlignment(Qt.AlignVCenter|Qt.AlignRight)
        self.ui.comboBoxPage.view().model().item(1).setTextAlignment(Qt.AlignVCenter|Qt.AlignRight)
        self.ui.comboBoxPage.view().model().item(2).setTextAlignment(Qt.AlignVCenter|Qt.AlignRight)
        self.ui.comboBoxPage.view().model().item(3).setTextAlignment(Qt.AlignVCenter|Qt.AlignRight)
        # self.ui.comboBoxPage.view().setStyleSheet("padding-right:10px;")

        self.ui.pushButtonSwitch.setIcon(QIcon(QPixmap(":/resources/列表.png")))
        self.ui.pushButtonSwitch.setToolTip(QtCore.QCoreApplication.translate("Main", "列表视图"))
        self.ui.pushButtonPage1.setText(str(1))
        self.ui.pushButtonPage2.setText('...')
        self.ui.pushButtonPage3.setText(str(self.totalPage))
        self.ui.pushButtonPage1.setStyleSheet('color: white; border: 1px solid #fff;')
        self.ui.widgetListTitle.setVisible(False)
        self.updateButtonIcon()  # 初始化文件列表图标按钮
        self.ui.tBtnCollapse.setToolTip(QtCore.QCoreApplication.translate("Main", "折叠"))
        tooltip = self.ui.tBtnCollapse.toolTip()
        if tooltip == "折叠":
            self.ui.tBtnCollapse.setIcon(
                QtGui.QIcon("D:\pycharm_python_project\Annotation-master\wisdom_store\wins\收起列表新.png"))
            # 设置按钮图标为“收起列表”图标
        self.state_scrollAreaPreview_hide = False  # 默认显示预览窗格
        self.ui.widgetFileListPanel.setVisible(True)  # 默认显示文件列表
        self.actionFileList.setChecked(True)  # 默认选中菜单项


        self.ctrl_state = 0
        self.angle = 0
        self.enhanceThreadfinished = True

    def signalConnect(self):
        '''
        信号槽绑定
        :return:
        '''
        # 左侧工具栏
        self.ui.tBtnCollapse.clicked.connect(self.slotChangeScrollAreaPreviewHide)
        self.ui.tBtnHand.clicked.connect(self.slotTBtnHand)
        self.ui.tBtnArrow.clicked.connect(self.slotTBtnArrow)
        self.ui.tBtnBrush.clicked.connect(self.slotTBtnBrush)
        self.ui.tBtnZoom.clicked.connect(self.slotTBtnZoom)
        self.ui.tBtnRectangleLabel.clicked.connect(self.slotTBtnRect)
        self.ui.tBtnPolygonLabel.clicked.connect(self.slotTBtnPoly)
        self.ui.tBtnLine.clicked.connect(self.slotTBtnLine)
        self.ui.tBtnPointLabel.clicked.connect(self.slotTBtnPoint)
        self.ui.tBtnTag.clicked.connect(self.slotTBtnTag)
        self.ui.tBtnCircle.clicked.connect(self.slotTBtnCircle)
        self.ui.tBtnAIAnalysis.clicked.connect(self.slotTBtnAIAnalysis)
        self.ui.tBtnAIMagic.clicked.connect(self.slotTBtnAIMagic)

        self.MainGraphicsView.paintUsed.connect(self.ui.tBtnArrow.click)
        self.MainGraphicsView.scaleChanged.connect(self.updateComboBoxZoomValue)
        # 画刷大小
        self.ui.horizontalSliderBrushSize.valueChanged.connect(self.setBrushValue)
        self.MainGraphicsView.changeScrawPenSize.connect(self.changeBrushValue)
        self.MainGraphicsView.changeThresholdValue.connect(self.changeThresholdValue)
        # self.ui.horizontalSliderSensibility.valueChanged.connect(self.setSensibilityValue)

        # 右侧TabWidget切换
        self.ui.toolButtonTypeList.clicked.connect(lambda: self.transWidgetStatistics(False, 0))
        self.ui.toolButtonTargetList.clicked.connect(lambda: self.transWidgetStatistics(False, 1))
        self.ui.toolButtonLog.clicked.connect(lambda: self.transWidgetStatistics(False, 2))
        # self.ui.toolButtonTypeListDetailed.clicked.connect(lambda: self.transStackedWidgetLabel(True, 0))
        # self.ui.toolButtonTargetListDetailed.clicked.connect(lambda: self.transStackedWidgetLabel(True, 1))
        # self.ui.toolButtonLogDetailed.clicked.connect(lambda: self.transStackedWidgetLabel(True, 2))

        # 设定目标类型
        self.ui.btnSetPartitonTag.clicked.connect(self.showSetParitionTagWin)

        # 弹窗绑定
        self.ui.tBtnToolsEdit.clicked.connect(self.showToolBoxSettingWin)
        self.ui.pBtnLogin.clicked.connect(lambda: self.showSubWinAndHideMain(self.loginWin))

        self.ui.tBtnStatisticalAnalysis.clicked.connect(self.showStatisticAnalyseWin)

        # 顶部工具栏
        self.ui.labelPartitionColor.mousePressEvent = lambda event: self.showSetParitionTagWin()
        self.ui.toolButtonSetting.clicked.connect(self.showSetParitionTagWin)
        self.ui.comboBoxTags.currentTextChanged.connect(self.updateTopBarColor)
        self.ui.comboBoxTags.currentTextChanged.connect(self.setTargetSideBar)
        self.ui.comboBoxTags.currentTextChanged.connect(self.setTypeSideBar)
        self.ui.comboBoxModel.currentTextChanged.connect(self.updateAiModel)
        self.ui.pBtnFitScreen.clicked.connect(self.MainGraphicsView.fitScreen)
        self.ui.pBtnFullScreen.clicked.connect(self.MainGraphicsView.fullScreen)
        self.ui.comboBoxZoomValue.currentTextChanged.connect(
            lambda newtext: self.MainGraphicsView.setScale(int(newtext.replace("%", "")) / 100))
        self.ui.tBtnEnlarge.clicked.connect(self.slotTBtnEnlarge)
        self.ui.tBtnNarrow.clicked.connect(self.slotTBtnNarrow)
        self.ui.tBtnFill.clicked.connect(self.slotTBtnFill)
        self.ui.spinBoxPixelValue.textChanged.connect(lambda newtext: self.MainGraphicsView.changeAlpha(int(newtext)))

        self.ui.toolButtonUndo.setDefaultAction(self.MainGraphicsView.undoAction)
        self.ui.toolButtonRedo.setDefaultAction(self.MainGraphicsView.redoAction)

        self.ui.toolButtonChangeRawImg.pressed.connect(self.loadRawImg)
        #A修改（下面无空行的代码均修改过，直接复制粘贴）
        self.ui.toolButtonChangeRawImg.pressed.connect(self.recordToolStateBeforePress)
        self.ui.toolButtonChangeRawImg.pressed.connect(lambda : self.MainGraphicsView.toggleCenterPoints())
        self.ui.toolButtonChangeRawImg.released.connect(lambda: self.MainGraphicsView.temporalLoadRawImage())
        self.ui.toolButtonChangeRawImg.released.connect(lambda: self.MainGraphicsView.toggleCenterPoints())
        self.MainGraphicsView.changeIconSignal.connect(self.changeIcon)
        self.ui.toolButtonChangeRawImg.released.connect(lambda: self.MainGraphicsView.requestRestoreTool.emit())
        self.MainGraphicsView.requestRestoreTool.connect(self.restoreToHandTool)

        self.actionImportNewData.triggered.connect(self.importNewImage)



        # 画刷模式与橡皮擦模式
        self.ui.tBtnScrawBrushmode.pressed.connect(self.SwitchScrawBrushmode)
        self.ui.tBtnScrawErasermode.pressed.connect(self.SwitchScrawErasemode)

        # 多边形涂鸦转换
        self.ui.tBtnToPolygonLabel.pressed.connect(lambda: self.convertScrawToPolygon())
        self.ui.tBtnToScrawLabel.pressed.connect(lambda: self.convertPolygonToSraw())

        # 多边形智慧剪刀切换
        self.ui.tBtnIntelligentScissors.setCheckable(True)
        self.ui.tBtnOriginPolygonLabel.setCheckable(True)
        self.ui.tBtnIntelligentScissors.clicked.connect(self.slotTBtnIntelligentScissors)
        self.ui.tBtnOriginPolygonLabel.clicked.connect(self.slotTBtnPoly)
        # 设置滑动条的范围
        self.ui.PointNumSlider.setMinimum(1)
        self.ui.PointNumSlider.setMaximum(20)
        self.ui.PointNumSlider.setSingleStep(2)

        self.ui.PointNumSlider.valueChanged.connect(self.updatePointNum)
        self.ui.PointNumSlider.setValue(self.MainGraphicsView.ScissorspPointNum)

        self.ui.PointNum.setText(f"点间隔:")
        self.ui.PointNumSlider.setVisible(False)
        self.ui.PointNum.setVisible(False)

        self.ui.ScissorsAreaSlider.setMinimum(40)
        self.ui.ScissorsAreaSlider.setMaximum(512)
        # 连接滑动条的信号到槽
        self.ui.ScissorsAreaSlider.valueChanged.connect(self.updateScissorsArea)
        self.ui.ScissorsAreaSlider.setValue(self.MainGraphicsView.square_size)
        # 初始化标签显示
        self.ui.ScissorsArea.setText(f"搜索区域:")
        self.ui.ScissorsAreaSlider.setVisible(False)
        self.ui.ScissorsArea.setVisible(False)

        # 悬浮模式点击模式启动与关闭
        self.ui.tBtnClickmode.pressed.connect(self.SwitchClickmodeon)
        self.ui.tBtnHovermode.pressed.connect(self.SwitchHovermodeon)

        # 画框模式的启动
        self.ui.tBtnRectmode.pressed.connect(self.SwitchRectmodeon)

        # 智能标注内画刷与橡皮擦的启动
        self.ui.tBtnBrushmode.pressed.connect(self.SwitchBrushmodeon)
        self.ui.tBtnErasermode.pressed.connect(self.SwitchErasermodeon)

        # 右侧折叠栏
        self.ui.toolButtonManipulationOpen.clicked.connect(lambda: self.transWidgetManipulation(self.ManipulationState))
        self.ui.toolButtonManipulationToBrief.clicked.connect(lambda: self.transWidgetManipulation(True))
        self.ui.toolButtonStatisticsOpen.clicked.connect(lambda: self.transWidgetStatistics(self.StatisticsState, 0))
        self.ui.toolButtonStatisticsToBrief.clicked.connect(lambda: self.transWidgetStatistics(True))
        self.ui.pushButtonEnhancement.clicked.connect(lambda: self.transWidgetEnhancement())
        self.ui.pushButtonSegmentation.clicked.connect(lambda: self.transWidgetSegmentation())
        #1修改 ，窗口的切换槽函数
        self.ui.pushButtonProcessing.clicked.connect(lambda: self.transWidgetProcessing())
        self.ui.pBtnReset.clicked.connect(self.showResetWin)

        # 统计栏
        self.ui.tableWidget.cellDoubleClicked.connect(self.changeType)
        # 允许选中多行
        self.ui.tableWidgetTargetList.setSelectionMode(QTableWidget.ExtendedSelection)
        self.ui.tableWidgetTargetList.setSelectionBehavior(QTableWidget.SelectRows)
        # self.ui.tableWidgetTargetList.cellClicked.connect(self.selectRuler)
        # self.ui.tableWidgetTargetList.cellDoubleClicked.connect(self.showChangeType)
        self.ui.tableWidgetTargetList.cellClicked.connect(self.handleCellClick)
        self.ui.tableWidgetTargetList.cellDoubleClicked.connect(self.handleCellDoubleClick)

        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.processSingleClick)

        # 底部
        self.MainGraphicsView.pixelString.connect(self.updatePixelString)
        # 亮度对比度饱和度
        # self.brightnessContrastAdjustmentWin.BrightnessContrastChanged.connect(self.MainGraphicsView.updateBrightContrast) # 弃用
        self.brightnessContrastAdjustmentWin.BrightnessChanged.connect(lambda brightness: self.moveBCS(brightness, None, None))
        self.brightnessContrastAdjustmentWin.ContrastChanged.connect(lambda contrast: self.moveBCS(None, contrast, None))
        self.brightnessContrastAdjustmentWin.SaturationChanged.connect(lambda saturation: self.moveBCS(None, None, saturation))
        self.brightnessContrastAdjustmentWin.BCSChanged.connect(self.moveBCS)
        # self.brightnessContrastAdjustmentWin.BrightnessChanged.connect(self.MainGraphicsView.updateBrightness)
        # self.brightnessContrastAdjustmentWin.ContrastChanged.connect(self.MainGraphicsView.updateContrast)
        # self.brightnessContrastAdjustmentWin.SaturationChanged.connect(self.MainGraphicsView.updateSaturation)
        #   标注展示
        self.tagShowWin.AlphaChanged.connect(self.MainGraphicsView.changeAlpha)
        self.tagShowWin.AlphaSelectChanged.connect(self.MainGraphicsView.changeAlphaSelect)
        #1修改 右侧折叠栏标注展示
        self.labelShowWin.AlphaChanged.connect(self.MainGraphicsView.changeAlpha)
        self.labelShowWin.AlphaSelectChanged.connect(self.MainGraphicsView.changeAlphaSelect)
        #self.labelShowWin.InstanceColorChanged.connect(self.MainGraphicsView.chengeInstanceColor) #实例颜色不着急，这一部分先空着
        #1修改 形态学变换的信号连接
        self.morphologyWin.TargetTypeChanged.connect(self.MainGraphicsView.handleMorphologyTargetTypeChanged)
        self.morphologyWin.OperationTypeChanged.connect(self.MainGraphicsView.handleMorphologyOperationChanged)
        self.morphologyWin.ParameterChanged.connect(self.MainGraphicsView.handleMorphologyParameterChanged)
        self.morphologyWin.MorphologyReset.connect(self.MainGraphicsView.resetMorphologyPreview)
        self.morphologyWin.MorphologyConfirm.connect(self.MainGraphicsView.confirmMorphologyApplication)

        # 主视图
        self.ui.horizontalSliderThreshold.valueChanged.connect(self.setResThreshold)
        self.ui.pBtnThresholdEnsure.clicked.connect(self.thresholdEnsure)

        # 分页
        self.ui.pushButtonFilter.clicked.connect(self.showFilterWin)
        self.ui.comboBoxPage.currentTextChanged.connect(lambda: self.refreshPage(1))
        self.ui.pushButtonSwitch.clicked.connect(lambda: self.refreshPage(self.currentPage, True))
        self.ui.pushButtonPrePage.clicked.connect(lambda: self.refreshPage(self.currentPage - 1 if self.currentPage - 1 >= 1 else 1))
        self.ui.pushButtonNextPage.clicked.connect(lambda: self.refreshPage(self.currentPage + 1 if self.currentPage + 1 <= self.totalPage else self.totalPage))
        self.ui.pushButtonHomePage.clicked.connect(lambda: self.refreshPage(1))
        self.ui.pushButtonFinalPage.clicked.connect(lambda: self.refreshPage(self.totalPage))
        self.ui.pushButtonPage1.clicked.connect(lambda : self.refreshPage(self.ui.pushButtonPage1.text()))
        self.ui.pushButtonPage2.clicked.connect(lambda : self.refreshPage(self.ui.pushButtonPage2.text()))
        self.ui.pushButtonPage3.clicked.connect(lambda : self.refreshPage(self.ui.pushButtonPage3.text()))

        # 快捷键
        keyboard.add_hotkey('ctrl+c', self.copylabel)
        keyboard.add_hotkey('ctrl+v', self.bridge)
        keyboard.on_press_key("ctrl", self.ctrl_event)
        keyboard.on_release_key("ctrl", self.ctrl_event)
        self.signal2.connect(self.pastelabel)

    #A修改（增加了changeIcon、recordToolStateBeforePress、restoreToHandTool函数）
    def changeIcon(self, isShiftVPressed):
        if isShiftVPressed:
            self.ui.toolButtonChangeRawImg.setIcon(QIcon(":/resources/原图-选中.png"))
        else:
            self.ui.toolButtonChangeRawImg.setIcon(QIcon(":/resources/原图.png"))

    def recordToolStateBeforePress(self):
        if self.ui.tBtnArrow.isChecked():
            self.MainGraphicsView.previous_tool = "edit"
        else:
            self.MainGraphicsView.previous_tool = None

    def restoreToHandTool(self):
        if hasattr(self.MainGraphicsView, 'previous_tool') and self.MainGraphicsView.previous_tool == "edit":
            self.ui.tBtnHand.setChecked(True)  # 切换到手势工具
            self.slotTBtnHand()

    def setProject(self, project: Project):
        self.project = project

    # 子窗口唤出
    def showSubWinAndHideMain(self, subWin):
        if len(self.project.classes) == 0:
            dlg = Dialog('请先在编辑-设定目标类型中设置标签')
            dlg.exec()
            self.ui.tBtnArrow.click()
            return
        elif len(self.fileList) == 0:
            dlg = Dialog('请先添加图片')
            dlg.exec()
            self.ui.tBtnArrow.click()
            return
        subWin.setWindowModality(Qt.WindowModality.ApplicationModal)
        subWin.show()
        # self.hide()

    #子窗口隐藏
    def hideSubWinAndShowMain(self, subWin):
        subWin.hide()
        self.show()

    # 子窗口无检查唤出
    def showSubWinAndHideMainNoCheck(self, subWin):
        subWin.setWindowModality(Qt.WindowModality.ApplicationModal)
        subWin.show()

    #分页筛选
    def showFilterWin(self):
        if (len(self.fileList) == 0 and not hasattr(self, 'filterWin')) \
            or (len(self.fileList) == 0 and hasattr(self, 'filterWin') and self.filterWin.isFiltered == False):
            dlg = Dialog('请先添加图片')
            dlg.exec()
            self.ui.tBtnArrow.click()
            return
        if 0 < self.ui.listwidgetFile.currentRow() + self.pageSize * (self.currentPage-1) < len(self.fileList):
            self.save(self.fileList[self.ui.listwidgetFile.currentRow() + self.pageSize * (self.currentPage-1)].get('path'))
        t_fileList = copy.deepcopy(self.project.importFiles)
        for i in range(len(t_fileList)):  # 相对路径转为绝对路径
            raw_img = os.path.join(self.project.rawDataDir, t_fileList[i]['path'])
            modified_img = os.path.join(self.project.modifiedImgDir, t_fileList[i]['path'])
            if os.path.exists(modified_img):
                t_fileList[i]['path'] = modified_img
            else:
                t_fileList[i]['path'] = raw_img
        if not hasattr(self, 'filterWin'):
            self.filterWin = FilterWin(self, t_fileList, self.project)
            self.filterWin.signalFilterRes.connect(self.filterFile)
        else:
            self.filterWin.updateFileList(t_fileList)
        self.filterWin.show()

    def filterFile(self, filterFileList):
        if len(filterFileList) == len(self.project.importFiles):
            self.filterWin.isFiltered = False
            self.ui.pushButtonFilter.setIcon(QIcon(QPixmap(":/resources/筛选.png")))
        else:
            self.filterWin.isFiltered = True
            self.ui.pushButtonFilter.setIcon(QIcon(QPixmap(":/resources/已筛选.png")))
        self.fileList = filterFileList
        self.fileNameList = [item['path'].split("\\")[-1] for item in self.fileList]
        self.lastFileIndex = -1
        self.refreshPage(1)

    #侧边栏图像增强窗口唤出
    def showFoldingEnhancementWin(self, subWin):
        if len(self.project.classes) == 0:
            dlg = Dialog('请先在编辑-设定目标类型中设置标签')
            dlg.exec()
            self.ui.tBtnArrow.click()
            return
        elif len(self.fileList) == 0:
            dlg = Dialog('请先添加图片')
            dlg.exec()
            self.ui.tBtnArrow.click()
            return
        self.transWidgetManipulation(False)
        self.transWidgetEnhancement()
        self.actionManipulation.setChecked(True)
        subWin.ui.toolButtonFold.setChecked(True)
        subWin.trans()

    #侧边栏图像分割窗口唤出
    def showFoldingSegmentationWin(self, subWin):
        if len(self.project.classes) == 0:
            dlg = Dialog('请先在编辑-设定目标类型中设置标签')
            dlg.exec()
            self.ui.tBtnArrow.click()
            return
        elif len(self.fileList) == 0:
            dlg = Dialog('请先添加图片')
            dlg.exec()
            self.ui.tBtnArrow.click()
            return
        self.transWidgetManipulation(False)
        self.transWidgetSegmentation()

        subWin.ui.toolButtonFold.setChecked(True)
        subWin.trans()

    #1修改
    #侧边栏图像标注后处理窗口唤出
    def showFoldingProcessingWin(self,subWin):
        if len(self.project.classes) == 0:
            dlg = Dialog('请先在编辑-设定目标类型中设置标签')
            dlg.exec()
            self.ui.tBtnArrow.click()
            return
        elif len(self.fileList) == 0:
            dlg = Dialog('请先添加图片')
            dlg.exec()
            self.ui.tBtnArrow.click()
            return
        self.transWidgetManipulation(False)
        self.transWidgetProcessing()
        subWin.ui.toolButtonFold.setChecked(True)
        subWin.trans()



    def showMainAndSetUserInfo(self):
        self.show()
        self.ui.pBtnLogin.setEnabled(False)
        self.ui.pBtnUserOp.show()
        # 设置用户名
        # self.ui.pBtnLogin.setText(api.user['username'])
        self.ui.pBtnLogin.setText(user.account)
        # 设置头像
        # TODO: 等待接口增加头像字段后设置
        # self.loginWin.setAvatar(api.user['avatar'], self.ui.labelAvatar)

    def showSetParitionTagWin(self):
        if len(self.project.classes) == 0:
            dlg = Dialog('请先在编辑-设定目标类型中设置标签')
            dlg.exec()
            self.ui.tBtnArrow.click()
            return
        elif len(self.fileList) == 0:
            dlg = Dialog('请先添加图片')
            dlg.exec()
            self.ui.tBtnArrow.click()
            return
        # self.changeFile(self.ui.listwidgetFile.currentRow())
        self.save(self.fileList[self.ui.listwidgetFile.currentRow() + self.pageSize * (self.currentPage-1)].get('path'))
        self.setPartitionTagWin = None
        self.setPartitionTagWin = SetPartitionTag(self.project, self)
        self.setPartitionTagWin.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setPartitionTagWin.PartitionChanged.connect(self.updateLabelColor)
        self.setPartitionTagWin.show()

    # 打开标尺设置窗口
    def showSetRulerWin(self):
        '''
        标尺窗口
        '''
        if len(self.fileList) == 0:
            dlg = Dialog('请先添加图片')
            dlg.exec()
            self.ui.tBtnArrow.click()
            return
        self.setRulerWin = None
        self.setRulerWin = SetRuler(self.fileList, self.project)
        if self.flagStatisticAnalyseWin:
            self.setRulerWin.ui.tBtnClose.clicked.connect(self.statisticAnalyseWin.show)
            self.flagStatisticAnalyseWin = False
        else:
            try:
                self.setRulerWin.ui.tBtnClose.clicked.disconnect(self.statisticAnalyseWin.show)
            except:
                pass
        self.setRulerWin.SignalUserRulerLabel.connect(self.userRulerLabel)
        self.setRulerWin.show()

    # 选择文件进行人工标定
    def userRulerLabel(self, index):
        # # 刷新文件列表为全部
        # t_fileList = copy.deepcopy(self.project.importFiles)
        # for i in range(len(t_fileList)):  # 相对路径转为绝对路径
        #     raw_img = os.path.join(self.project.rawDataDir, t_fileList[i]['path'])
        #     modified_img = os.path.join(self.project.modifiedImgDir, t_fileList[i]['path'])
        #     if os.path.exists(modified_img):
        #         t_fileList[i]['path'] = modified_img
        #     else:
        #         t_fileList[i]['path'] = raw_img
        # self.filterFile(t_fileList)
        # 切换到选中的页面
        if self.currentPage != int(index / self.pageSize + 1):
            self.refreshPage(index / self.pageSize + 1)
        self.ui.listwidgetFile.setCurrentRow(index - self.pageSize * (self.currentPage - 1))
        self.labelCreatingLock(False)
        # 初始化为人工标定状态
        self.slotTBtnRuler()

    # 打开单图标尺设置窗口
    def showSetRulerSingleImageWin(self, pixLen):
        self.setRulerSingleImageWin = None
        self.setRulerSingleImageWin = SetRulerSingleImage(pixLen)
        self.setRulerSingleImageWin.setWindowModality(Qt.WindowModality.ApplicationModal)
        # 信号绑定
        self.setRulerSingleImageWin.singleClose.connect(self.closeRuler)
        self.setRulerSingleImageWin.singleConfirm.connect(self.safeScale)
        self.setRulerSingleImageWin.show()

    def safeScale(self, scale, scaleMeasurement):
        index = (self.currentPage - 1) * self.pageSize +self.ui.listwidgetFile.currentRow()
        self.fileList[index]["scale"] = scale
        self.fileList[index]["scaleMeasurement"] = scaleMeasurement
        for file in self.project.importFiles:
            path = self.fileList[index]["path"].split("\\")[-1]
            if file["path"] == path:
                file["scale"] = scale
                file["scaleMeasurement"] = scaleMeasurement
                break
        # self.project.importFiles[index]["scale"] = scale
        # self.project.importFiles[index]["scaleMeasurement"] = scaleMeasurement
        self.project.save()

    # 取消标尺设置[单窗口叉、单窗口点取消、右键取消等]
    def closeRuler(self):
        self.labelCreatingLock(True)
        self.ui.tBtnHand.click()
        self.MainGraphicsView.mutex.unlock()
        # 清除视图上的标尺标注
        self.MainGraphicsView.myScene.removeItem(self.MainGraphicsView.rulerLabel)
        self.MainGraphicsView.rulerLabel = None
        # 回到标尺设置页面
        self.showSetRulerWin()


    # 打开统计分析窗口
    def showStatisticAnalyseWin(self):
        self.ui.widgetFileListPanel.setVisible(True)  # 默认显示文件列表
        self.actionFileList.setChecked(True)  # 默认选中菜单项

        if len(self.project.classes) == 0:
            dlg = Dialog('请先在编辑-设定目标类型中设置标签')
            dlg.exec()
            self.ui.tBtnArrow.click()
            return
        elif len(self.fileList) == 0:
            dlg = Dialog('请先添加图片')
            dlg.exec()
            self.ui.tBtnArrow.click()
            return
        #self.changeFile(self.ui.listwidgetFile.currentRow())
        self.save(self.fileList[self.ui.listwidgetFile.currentRow() + self.pageSize * (self.currentPage-1)].get('path'))
        self.hideBtnSetting()
        # if self.config.isAuth:
        #     if not checkPermission(self, self.auth):
        #         return
        self.statisticAnalyseWin = None
        self.statisticAnalyseWin = StatisticAnalyseWin(self.config, self.project, self.auth)
        self.statisticAnalyseWin.signalClose.connect(self.refreshTools)
        self.statisticAnalyseWin.signalSetRuler.connect(self.setFlagTrue)
        self.statisticAnalyseWin.signalSetRuler.connect(self.statisticAnalyseWin.close)
        self.statisticAnalyseWin.signalSetRuler.connect(self.showSetRulerWin)
        fileLabelState = []
        for fileDict in self.fileList:
            if fileDict.get('labelCompleted'):
                fileLabelState.append('Manual')  # 手工标注
            elif fileDict.get('inferCompleted'):
                fileLabelState.append('Infer')  # 推理标注
            else:
                fileLabelState.append(False)
        # fileLabelState = [(fileDict.get('labelCompleted') or fileDict.get('inferCompleted')) for fileDict in self.fileList]
        self.statisticAnalyseWin.importFiles(self.fileList, fileLabelState, self.lastFileIndex)
        # self.statisticAnalyseWin.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.statisticAnalyseWin.show()

    def setFlagTrue(self):
        self.flagStatisticAnalyseWin = True

    def showDeleteSelectionWin(self, modelIndexRow=-2):
        self.DeleteSelectionWin = None
        self.DeleteSelectionWin = DeleteSelectionWin(modelIndexRow)
        self.DeleteSelectionWin.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.DeleteSelectionWin.signalClose.connect(self.showDeleteWarningWin)
        self.DeleteSelectionWin.show()

    def showDeleteWarningWin(self, warningType, modelIndexRow=-2):
        if len(self.project.classes) == 0:
            dlg = Dialog('请先在编辑-设定目标类型中设置标签')
            dlg.exec()
            self.ui.tBtnArrow.click()
            return
        elif len(self.fileList) == 0:
            dlg = Dialog('请先添加图片')
            dlg.exec()
            self.ui.tBtnArrow.click()
            return
        if (modelIndexRow == -1):
            modelIndexRow = 0
        else:
            modelIndexRow = modelIndexRow + self.pageSize * (self.currentPage - 1)
        # print('delete:', modelIndexRow)
        self.DeleteWarningWin = None
        self.DeleteWarningWin = DeleteWarningWin(warningType, modelIndexRow, self.ui.listwidgetFile,
                                                 self.fileList, self.MainGraphicsView.getLabelList(), self.project,
                                                 self)
        self.DeleteWarningWin.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.DeleteWarningWin.signalClose.connect(self.showDeleteSelectionWin)
        self.DeleteWarningWin.show()

    def showToolBoxSettingWin(self):
        self.toolBoxSettingWin = ToolBoxSettingWindow(self.project)
        self.toolBoxSettingWin.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.toolBoxSettingWin.signalRefreshTools.connect(self.refreshTools)
        self.toolBoxSettingWin.show()

    def refreshTools(self, isNeedRefreshTools=True):
        if isNeedRefreshTools:
            tools = self.project.toolButtons
            for tool in tools:
                toolObj = self.getToolObjByName(tool['name'])
                if toolObj is None:
                    continue
                activate = tool['activate']
                if activate:
                    toolObj.show()
                else:
                    toolObj.hide()
        self.ui.tBtnToolsEdit.setAutoExclusive(False)
        self.ui.tBtnToolsEdit.setChecked(False)
        self.ui.tBtnToolsEdit.setAutoExclusive(True)
        self.ui.tBtnStatisticalAnalysis.setAutoExclusive(False)
        self.ui.tBtnStatisticalAnalysis.setChecked(False)
        self.ui.tBtnStatisticalAnalysis.setAutoExclusive(True)

    def refreshPage(self, pageNum, isNeedSwitch=False):
        self.pageSize = int(re.findall("\d+\d*", self.ui.comboBoxPage.currentText())[0])
        self.totalPage = math.ceil(len(self.fileList) / self.pageSize)
        # print(pageNum, self.pageSize)
        if pageNum == '...':
            return
        else:
            pageNum = int(pageNum)
        if len(self.fileList) == 0:
            self.totalPage = 1
            self.ui.tBtnHand.click()
            self.MainGraphicsView.initState()
            self.MainGraphicsView.handTool = True
            self.MainGraphicsView.birdViewShow = True
            self.MainGraphicsView.setDragMode(QGraphicsView.ScrollHandDrag)
            self.MainGraphicsView.setCursor(Qt.OpenHandCursor)
            self.MainGraphicsView.changeZoomMode(zoomMode.NoZoom)
            self.MainGraphicsView.viewport().update()
            self.labelCreatingLock(False)
            self.ui.pushButtonFilter.setEnabled(True)
            self.ui.toolButtonHome.setEnabled(True)
            self.actionBackHome.setEnabled(True)
            self.actionExit.setEnabled(True)
            if not hasattr(self, 'filterWin') or \
                hasattr(self, 'filterWin') and self.filterWin.isFiltered == False:
                self.actionImportNewData.setEnabled(True)
                self.actionImportNewDataAndLabel.setEnabled(True)
        else:
            self.labelCreatingLock(True)
        if pageNum < 1 or pageNum > self.totalPage:
            return
        self.currentPage = pageNum
        self.ui.listwidgetFile.currentRowChanged.disconnect()
        self.ui.listwidgetFile.clear()
        # 切换图片显示
        if isNeedSwitch:
            self.useThumbnail = not self.useThumbnail
            if self.useThumbnail == True:
                self.ui.widgetListTitle.setVisible(False)
                self.ui.pushButtonSwitch.setIcon(QIcon(QPixmap(":/resources/列表.png")))
                self.ui.pushButtonSwitch.setToolTip(QtCore.QCoreApplication.translate("Main", "列表视图"))
            else:
                self.ui.widgetListTitle.setVisible(True)
                self.ui.pushButtonSwitch.setIcon(QIcon(QPixmap(":/resources/缩略图.png")))
                self.ui.pushButtonSwitch.setToolTip(QtCore.QCoreApplication.translate("Main", "缩略图视图"))

        for file in self.fileList[self.pageSize * (self.currentPage-1) : self.pageSize * self.currentPage]:
            self.addNewFile(file["path"], file["labelCompleted"], file["inferCompleted"])
        self.ui.listwidgetFile.currentRowChanged.connect(self.changeFile)

        self.ui.pushButtonPage1.setStyleSheet('color: #1e2537;')
        self.ui.pushButtonPage2.setStyleSheet('color: #1e2537;')
        self.ui.pushButtonPage3.setStyleSheet('color: #1e2537;')

        if pageNum == 1:
            self.ui.pushButtonPage1.setText(str(1))
            self.ui.pushButtonPage2.setText('...')
            self.ui.pushButtonPage3.setText(str(self.totalPage))
            self.ui.pushButtonPage1.setStyleSheet('color:white;border: 1px solid #fff;')
        elif pageNum == self.totalPage:
            self.ui.pushButtonPage1.setText(str(1))
            self.ui.pushButtonPage2.setText('...')
            self.ui.pushButtonPage3.setText(str(self.totalPage))
            self.ui.pushButtonPage3.setStyleSheet('color:white;border: 1px solid #fff;')
        else:
            self.ui.pushButtonPage1.setText('...')
            self.ui.pushButtonPage2.setText(str(pageNum))
            self.ui.pushButtonPage3.setText('...')
            self.ui.pushButtonPage2.setStyleSheet('color:white;border: 1px solid #fff;')

        self.MainGraphicsView.myScene.clear()
        self.MainGraphicsView.scrawCursor = None
        self.MainGraphicsView.birdViewShow = False
        self.birdView.setVisible(False)
        self.ui.listwidgetFile.setCurrentRow(0)
        self.updateLabelFileDescription()
        # self.changeFile(0)


    '''
    窗口顶部菜单
    '''

    def createMenus(self):
        '''
        动态创建菜单
        :return:
        '''
        # =====用户登录相关操作=====
        menuLogin = QMenu(' ')
        self.actionSwitchAccount = menuLogin.addAction('切换用户')
        self.actionLogout = menuLogin.addAction('退出登录')
        menuLogin.setStyleSheet(Style_QMenu)
        self.ui.pBtnUserOp.setMenu(menuLogin)
        self.actionSwitchAccount.triggered.connect(
            lambda: self.loginWin.switchAccount(self.ui.labelAvatar, self.ui.pBtnLogin, self.ui.pBtnUserOp,
                                                self.loginWin, self))
        self.actionLogout.triggered.connect(
            lambda: self.loginWin.setLogout(self.ui.labelAvatar, self.ui.pBtnLogin, self.ui.pBtnUserOp))

        # =====上方菜单=====
        # 文件菜单
        menuFile = QMenu('文件')
        self.menuImportData = QMenu('导入数据')
        self.actionImportNewData = self.menuImportData.addAction('导入图像 (Ctrl+O)')
        self.actionImportNewDataAndLabel = self.menuImportData.addAction('导入图像与标注 (Ctrl+U)')
        menuFile.addMenu(self.menuImportData)
        self.actionLastImg = menuFile.addAction('上一张 (W)')
        self.actionNextImg = menuFile.addAction('下一张 (S)')
        self.actionExportLabel = menuFile.addAction('导出标注')
        self.menuDelete = QMenu('删除')
        self.actionDeleteImgAndLabel = self.menuDelete.addAction('删除本张图像及标注')
        self.actionDeleteAllImgAndLabel = self.menuDelete.addAction('删除所有图像及标注')
        self.actionDeleteLabel = self.menuDelete.addAction('删除本张标注 (Ctrl+Del)')
        self.actionDeleteAllLabel = self.menuDelete.addAction('删除所有标注')
        self.actionDeleteNoLabelImg = self.menuDelete.addAction('删除无标注图像')
        menuFile.addMenu(self.menuDelete)
        self.actionBackHome = menuFile.addAction('返回主界面 (Ctrl+Q)')
        self.actionExit = menuFile.addAction('退出 (Ctrl+Shift+Q)')

        self.actionImportNewDataAndLabel.triggered.connect(
            lambda: self.showSubWinAndHideMainNoCheck(self.importPictureAndLabelWin))
        self.actionExportLabel.triggered.connect(lambda: self.showSubWinAndHideMainNoCheck(self.exportWin))

        self.actionDeleteImgAndLabel.triggered.connect(
            lambda: self.showDeleteWarningWin(1, self.ui.listwidgetFile.currentRow()))
        self.actionDeleteAllImgAndLabel.triggered.connect(
            lambda: self.showDeleteWarningWin(2, self.ui.listwidgetFile.currentRow()))
        self.actionDeleteLabel.triggered.connect(
            lambda: self.showDeleteWarningWin(3, self.ui.listwidgetFile.currentRow()))
        self.actionDeleteAllLabel.triggered.connect(
            lambda: self.showDeleteWarningWin(4, self.ui.listwidgetFile.currentRow()))
        self.actionDeleteNoLabelImg.triggered.connect(
            lambda: self.showDeleteWarningWin(5, self.ui.listwidgetFile.currentRow()))

        # 编辑菜单
        menuEdit = QMenu('编辑')
        # self.action_forward = menuEdit.addAction("前进一步")
        # self.action_backward = menuEdit.addAction("后退一步")
        self.action_backward = menuEdit.addAction(self.MainGraphicsView.undoAction)
        self.action_forward = menuEdit.addAction(self.MainGraphicsView.redoAction)
        self.action_partition_label = menuEdit.addAction("设定目标类型")
        self.action_keep_label = menuEdit.addAction("保留上一张标注")
        self.action_keep_size = menuEdit.addAction("保留上一张尺寸")
        # self.action_unicom_division = menuEdit.addAction("联通区域划分")  # 暂时隐藏 TODO

        self.action_partition_label.triggered.connect(self.showSetParitionTagWin)
        # self.action_unicom_division.triggered.connect(lambda: self.regionDivideWin.show()) # 暂时隐藏 TODO

        # 图像菜单
        menuImg = QMenu('图像')
        self.menuImgEnhance = QMenu('图像增强')
        self.actionBrightnessContrast = self.menuImgEnhance.addAction('基本调整')
        self.actionHistogramAdjustments = self.menuImgEnhance.addAction('直方图调整')
        self.actionReversed = self.menuImgEnhance.addAction('反相')
        self.menuImgRotate = QMenu('图像旋转')
        self.actionAnyangle = self.menuImgRotate.addAction('任意角度')
        self.actionDNinty = self.menuImgRotate.addAction('180度')
        self.actionNintyRW = self.menuImgRotate.addAction('顺时针90度')
        self.actionNinty = self.menuImgRotate.addAction('逆时针90度')
        self.actionFlipH = self.menuImgRotate.addAction('水平翻转')
        self.actionFlipV = self.menuImgRotate.addAction('垂直翻转')
        # self.menuImgEnhance.addMenu(self.menuImgRotate)
        self.actionImgCrop = self.menuImgEnhance.addAction('图像裁剪')
        menuImg.addMenu(self.menuImgEnhance)
        # self.actionEdgeDetection = self.menuPreSegmentation.addAction('边缘检测')
        # self.actionLabelDisplay = menuImg.addAction('标注展示')
        # self.actionThermogram = menuImg.addAction('预测标注热力图')
        # self.actionStatisticalAnalysis = menuImg.addAction('统计分析')

        menuLabel = QMenu('标注')
        self.menuPreSegmentation = QMenu('图像预分割')
        self.actionThresholdSegmentation = self.menuPreSegmentation.addAction('阈值分割')
        menuLabel.addMenu(self.menuPreSegmentation)
        self.menuInteractiveLabel = QMenu('交互式标注')
        self.createRectangleLabel = self.menuInteractiveLabel.addAction('新建矩形 (R/Ctrl+R)')
        self.createPolygonLabel = self.menuInteractiveLabel.addAction('新建多边形 (P/N/Ctrl+P/Ctrl+N)')
        self.createBrushLabel = self.menuInteractiveLabel.addAction('新建涂鸦 (B/Ctrl+B)')
        self.createPointLabel = self.menuInteractiveLabel.addAction('新建点 (./Ctrl+.)')
        self.createLineLabel = self.menuInteractiveLabel.addAction('新建直线 (L/Ctrl+L)')
        self.createAILabel = self.menuInteractiveLabel.addAction('智能标注 (I/Ctrl+I/Ctrl+Shift+A)')
        self.Hand = self.menuInteractiveLabel.addAction('手势拖动 (H/Ctrl+H)')
        self.Edit = self.menuInteractiveLabel.addAction('编辑标注 (J/Ctrl+J)')
        menuLabel.addMenu(self.menuInteractiveLabel)

        self.menuLabelTransfer = QMenu('标注转换')
        self.ToPolygonLabel = self.menuLabelTransfer.addAction('涂鸦转多边形 (Shift+P)')
        self.ToScrawLabel = self.menuLabelTransfer.addAction('多边形转涂鸦 (Shift+B)')
        self.ScrawFill = self.menuLabelTransfer.addAction('涂鸦孔洞填充 (Shift+F)')
        menuLabel.addMenu(self.menuLabelTransfer)
        self.actionStatisticalAnalysis = menuLabel.addAction('统计分析 (Ctrl+Shift+S)')
        self.actionLabelDisplay = menuLabel.addAction('标注展示')
        self.actionEnhancedReset = menuImg.addAction('图像增强重置')
        self.menuRuler = menuImg.addAction('设置标尺')

        self.actionReversed.triggered.connect(self.imgReversePhase)
        self.actionBrightnessContrast.triggered.connect(
            lambda: self.showFoldingEnhancementWin(self.brightnessContrastAdjustmentWin))
        self.actionHistogramAdjustments.triggered.connect(
            lambda: self.showFoldingEnhancementWin(self.histogramAdjustmentWin))
        # self.actionEqualization.triggered.connect(lambda: self.showSubWinAndHideMain(self.equalizationWin))
        self.actionThresholdSegmentation.triggered.connect(
            lambda: self.showFoldingSegmentationWin(self.thresholdSegmentationWin))
        # self.actionEdgeDetection.triggered.connect(lambda: self.showSubWinAndHideMain(self.edgeDetectionWin))
        self.createRectangleLabel.triggered.connect(self.ui.tBtnRectangleLabel.click)
        self.createPolygonLabel.triggered.connect(self.ui.tBtnPolygonLabel.click)
        self.createPointLabel.triggered.connect(self.ui.tBtnPointLabel.click)
        self.createLineLabel.triggered.connect(self.ui.tBtnLine.click)
        self.createBrushLabel.triggered.connect(self.ui.tBtnBrush.click)
        self.createAILabel.triggered.connect(self.ui.tBtnAIMagic.click)
        self.Hand.triggered.connect(self.ui.tBtnHand.click)
        self.Edit.triggered.connect(self.ui.tBtnArrow.click)
        self.ToPolygonLabel.triggered.connect(self.ui.tBtnToPolygonLabel.click)
        self.ToScrawLabel.triggered.connect(self.ui.tBtnPolygonLabel.click)
        self.ToScrawLabel.triggered.connect(self.ui.tBtnToScrawLabel.click)
        self.ScrawFill.triggered.connect(self.ui.tBtnFill.click)

        self.actionLabelDisplay.triggered.connect(lambda: self.showSubWinAndHideMain(self.tagShowWin))
        self.actionStatisticalAnalysis.triggered.connect(self.showStatisticAnalyseWin)
        self.actionImgCrop.triggered.connect(self.slotTBtnCrop)

        self.actionAnyangle.triggered.connect(self.slotpushButtonImagerotation)
        self.actionDNinty.triggered.connect(lambda: self.actionRotate(0))
        self.actionNintyRW.triggered.connect(lambda: self.actionRotate(1))
        self.actionNinty.triggered.connect(lambda: self.actionRotate(-1))
        self.actionFlipH.triggered.connect(lambda: self.getflipcode(1))
        self.actionFlipV.triggered.connect(lambda: self.getflipcode(0))
        self.actionEnhancedReset.triggered.connect(self.resetEnhancedImg)
        self.menuRuler.triggered.connect(self.showSetRulerWin)

        # 视图菜单
        menuView = QMenu('视图')
        self.actionEnlarge = menuView.addAction("放大 (Ctrl++)")
        self.actionNarrow = menuView.addAction("缩小 (Ctrl+-)")
        self.actionFitScreen = menuView.addAction("适合屏幕 (Ctrl+Shift+W)")
        self.action_fill_screen = menuView.addAction("填充屏幕 (Ctrl+W)")

        self.actionEnlarge.triggered.connect(lambda: self.slotTBtnZoom(True))
        self.actionNarrow.triggered.connect(lambda: self.slotTBtnZoom(False))
        self.actionFitScreen.triggered.connect(self.MainGraphicsView.fitScreen)
        self.action_fill_screen.triggered.connect(self.MainGraphicsView.fullScreen)

        # 窗口菜单
        menu_window = QMenu('窗口')
        self.actionFileList = menu_window.addAction("文件列表")
        self.actionManipulation = menu_window.addAction("操作栏")
        self.actionStatistic = menu_window.addAction("统计栏")
        # self.actionTypeList = menu_window.addAction("类型列表")
        # self.actionStatisticsList = menu_window.addAction("目标列表")
        # self.actionOperateLog = menu_window.addAction("操作日志")

        # 设置QAction可勾选
        self.action_keep_label.setCheckable(True)
        self.action_keep_size.setCheckable(True)
        self.actionFileList.setCheckable(True)
        self.actionManipulation.setCheckable(True)
        self.actionStatistic.setCheckable(True)
        # self.actionTypeList.setCheckable(True)
        # self.actionStatisticsList.setCheckable(True)
        # self.actionOperateLog.setCheckable(True)

        # self.actionReversed.setCheckable(True)
        # 设置默认勾选状态
        self.action_keep_label.setChecked(False)
        self.action_keep_size.setChecked(False)
        self.actionFileList.setChecked(True)
        self.actionManipulation.setChecked(True)
        self.actionStatistic.setChecked(True)
        # self.actionTypeList.setChecked(True)
        # self.actionStatisticsList.setChecked(True)
        # self.actionOperateLog.setChecked(True)

        self.actionReversed.setChecked(False)
        # 帮助菜单
        menuHelp = QMenu('窗口')
        self.actionHelp = menuHelp.addAction("使用帮助")
        self.actionAactivation = menuHelp.addAction("解锁高级功能")
        self.actionUpdate = menuHelp.addAction("检查更新")
        self.actionAbout = menuHelp.addAction("关于")

        self.actionAactivation.triggered.connect(lambda: self.showSubWinAndHideMain(self.authWin))

        # 设置样式
        menuFile.setStyleSheet(Style_QMenu)
        self.menuImportData.setStyleSheet(Style_QMenu)
        self.menuDelete.setStyleSheet(Style_QMenu)
        menuEdit.setStyleSheet(Style_QMenu)
        menuImg.setStyleSheet(Style_QMenu)
        menuLabel.setStyleSheet(Style_QMenu)
        self.menuImgEnhance.setStyleSheet(Style_QMenu)
        self.menuImgRotate.setStyleSheet(Style_QMenu)
        self.menuPreSegmentation.setStyleSheet(Style_QMenu)
        self.menuInteractiveLabel.setStyleSheet(Style_QMenu)
        self.menuLabelTransfer.setStyleSheet(Style_QMenu)
        menuView.setStyleSheet(Style_QMenu)
        menu_window.setStyleSheet(Style_QMenu)
        menuHelp.setStyleSheet(Style_QMenu)

        # 将菜单绑定到QPushButton上
        self.ui.pBtnFile.setMenu(menuFile)
        self.ui.pBtnEdit.setMenu(menuEdit)
        self.ui.pBtnImage.setMenu(menuImg)
        self.ui.pBtnLabel.setMenu(menuLabel)
        self.ui.pBtnView.setMenu(menuView)
        self.ui.pBtnWindow.setMenu(menu_window)
        self.ui.pBtnHelp.setMenu(menuHelp)

        # 事件绑定
        self.MenuSignalConnect()

        # 调整menu下拉菜单宽度，解决文字显示补全问题（1080p正常）
        menuFile.setFixedWidth(menuFile.sizeHint().width() + 20)
        menuEdit.setFixedWidth(menuEdit.sizeHint().width() + 20)
        menuImg.setFixedWidth(menuImg.sizeHint().width() + 20)
        menuLabel.setFixedWidth(menuLabel.sizeHint().width() + 20)
        menuView.setFixedWidth(menuView.sizeHint().width() + 20)
        menu_window.setFixedWidth(menu_window.sizeHint().width() + 20)
        menuHelp.setFixedWidth(menuHelp.sizeHint().width() + 20)
        self.menuImportData.setFixedWidth(self.menuImportData.sizeHint().width() + 20)
        self.menuDelete.setFixedWidth(self.menuDelete.sizeHint().width() + 20)
        self.menuImgEnhance.setFixedWidth(self.menuImgEnhance.sizeHint().width() + 20)
        self.menuPreSegmentation.setFixedWidth(self.menuPreSegmentation.sizeHint().width() + 20)
        self.menuInteractiveLabel.setFixedWidth(self.menuInteractiveLabel.sizeHint().width() + 20)
        self.menuLabelTransfer.setFixedWidth(self.menuLabelTransfer.sizeHint().width() + 20)

        # 添加了菜单后，右侧下拉箭头遮挡了部分字体，需要调整宽度
        self.ui.pBtnFile.setFixedWidth(self.ui.pBtnFile.width() + 10)
        self.ui.pBtnEdit.setFixedWidth(self.ui.pBtnEdit.width() + 10)
        self.ui.pBtnImage.setFixedWidth(self.ui.pBtnImage.width() + 10)
        self.ui.pBtnLabel.setFixedWidth(self.ui.pBtnLabel.width() + 10)
        self.ui.pBtnModel.setFixedWidth(self.ui.pBtnModel.width() + 10)
        self.ui.pBtnView.setFixedWidth(self.ui.pBtnView.width() + 10)
        self.ui.pBtnWindow.setFixedWidth(self.ui.pBtnWindow.width() + 10)
        self.ui.pBtnHelp.setFixedWidth(self.ui.pBtnHelp.width() + 10)

        # ====左侧工具栏菜单====
        # 图像处理标注
        self.menuQuickLabel = QMenu('图像处理标注')
        self.actionThresholdSplitLabel = self.menuQuickLabel.addAction('阈值分割标注')
        icon1 = QIcon()
        icon1.addPixmap(QtGui.QPixmap(':/resources/阈值分割标注.png'), QtGui.QIcon.Normal)
        icon1.addPixmap(QtGui.QPixmap(':/resources/阈值分割标注-选中.png'), QtGui.QIcon.Active)
        self.actionThresholdSplitLabel.setIcon(icon1)
        self.ui.tBtnQuickLabel.setMenu(self.menuQuickLabel)
        self.menuQuickLabel.setStyleSheet(Style_QMenu)

        self.actionUpdate.triggered.connect(lambda: self.config.updateWin.show_and_checkUpdate(show_now=True))
        self.actionHelp.triggered.connect(lambda: open_url_by_browser(Config.HELP_URL))
        self.actionAbout.triggered.connect(self.showAbout)

    #A修改(增加onMenuActionClicked方法)
    def onMenuActionClicked(self):
        #菜单项点击后强制焦点回到 MainGraphicsView
        self.MainGraphicsView.forceFocus()

    def menuBar(self) -> QMenuBar:
        bar = super().menuBar()
        if hasattr(self, 'force_menu_visible') and self.force_menu_visible:
            bar.setVisible(True)
        return bar


    def showAbout(self):
        self.aboutWin = AboutWin()
        self.aboutWin.ui.labelIntroduction.setText(f"版本： v{Config.version}")
        self.aboutWin.show()

    def MenuSignalConnect(self):
        '''
        菜单事件绑定
        :return:
        '''
        # 文件菜单
        self.actionExit.triggered.connect(lambda: qApp.exit(0))
        self.actionNextImg.triggered.connect(
            lambda: self.switchImg(self.ui.listwidgetFile.currentRow() + 1))
        self.actionLastImg.triggered.connect(
            lambda: self.switchImg(self.ui.listwidgetFile.currentRow() - 1))

        # 编辑菜单
        # self.action_forward.triggered.connect()
        # self.action_backward.triggered.connect()
        # self.action_partition_label.triggered.connect()
        # self.action_unicom_division .triggered.connect()
        self.ui.listwidgetFile.currentRowChanged.connect(self.changeFile)
        self.ui.tableWidget.setColumnCount(5)
        self.ui.tableWidgetTargetList.setColumnCount(5)
        # self.ui.tableWidget.setHorizontalHeaderLabels(['全选', '类别', '数目'])
        # self.ui.tableWidgetTargetList.setHorizontalHeaderLabels(['类别', '置信度', '标注人'])

        self.ui.tableWidget.cellClicked.connect(self.changeShowHide)
        self.MainGraphicsView.labelNumChanged.connect(self.setTypeSideBar)
        self.MainGraphicsView.labelNumChanged.connect(self.setTargetSideBar)
        self.MainGraphicsView.labelNumChanged.connect(self.setCurLabelStatus)
        self.ui.tableWidgetTargetList.cellClicked.connect(self.setViewAtLabel)
        self.MainGraphicsView.labelCreateFinished.connect(self.labelCreatingLock)
        self.MainGraphicsView.singleAddLabelNum.connect(self.addLabelNum)
        self.MainGraphicsView.singleSubLabelNum.connect(self.subLabelNum)
        self.MainGraphicsView.rulerCreatingSuccess.connect(self.showSetRulerSingleImageWin)
        self.labelCreatingLock(True)

        # 窗口菜单
        self.actionFileList.triggered.connect(
            lambda: self.showOrHideWidgetByAction(self.actionFileList, self.ui.widgetFileListPanel))

        # 连接按钮的点击事件
        self.ui.tBtnCollapse.clicked.connect(
            lambda: self.showOrHideWidgetByAction(self.actionFileList, self.ui.widgetFileListPanel)
        )

        # 初始化按钮图标
        #self.updateButtonIcon()


        self.actionManipulation.triggered.connect(lambda: self.transWidgetManipulation(self.ManipulationState))
        self.actionStatistic.triggered.connect(lambda: self.transWidgetStatistics(self.StatisticsState, 0))

        # self.actionTypeList.triggered.connect(
        #     lambda: self.showOrHideWidgetByAction(self.actionTypeList, self.ui.toolButtonTypeList))
        # self.actionStatisticsList.triggered.connect(
        #     lambda: self.showOrHideWidgetByAction(self.actionStatisticsList, self.ui.toolButtonTargetList))
        # self.actionOperateLog.triggered.connect(
        #     lambda: self.showOrHideWidgetByAction(self.actionOperateLog, self.ui.toolButtonLog))

    def switchImg(self, targetRow):
        print(targetRow)
        if targetRow >= 0 and targetRow < self.pageSize:
            if targetRow >= self.ui.listwidgetFile.count():
                return
            self.ui.listwidgetFile.setCurrentRow(targetRow)
        else:
            if targetRow < 0 and self.currentPage > 1:
                self.refreshPage(self.currentPage - 1)
                self.ui.listwidgetFile.setCurrentRow(self.pageSize - 1)
            if targetRow < 0 and self.currentPage == 1:
                return
            if targetRow >= self.pageSize and self.currentPage < self.totalPage:
                self.refreshPage(self.currentPage + 1)
            if targetRow >= self.pageSize and self.currentPage == self.totalPage:
                return

    def showOrHideWidgetByAction(self, action: QAction, obj: QWidget or QToolButton):
        '''
        “窗口”菜单显示与隐藏的槽函数
        '''
        # 更新类型列表
        self.setTypeSideBar()
        # 更新目标列表
        self.setTargetSideBar()

        # 文件列表控件
        if obj == self.ui.widgetFileListPanel:
            if obj.isVisible():
                obj.hide()
                action.setChecked(False)
            else:
                obj.show()
                action.setChecked(True)

            self.updateButtonIcon()
            return

        # 其他控件的逻辑
        if action.isChecked():
            obj.show()
            targetList = [self.ui.toolButtonTypeList, self.ui.toolButtonTargetList, self.ui.toolButtonLog]
            if obj in targetList:
                obj.click()
                self.ui.tabWidget.show()
                self.transWidgetStatistics(False)
                self.ui.tabWidget.setCurrentIndex(targetList.index(obj))
        else:
            obj.hide()

            # 三个按钮均隐藏时，下方面板也要隐藏
            if self.ui.toolButtonTypeList.isHidden() and self.ui.toolButtonTargetList.isHidden() and self.ui.toolButtonLog.isHidden():
                self.ui.tabWidget.hide()

            # 隐藏的若是当前显示的面板，则需要切换
            if obj is self.ui.toolButtonTypeList and obj.isChecked():
                if not self.ui.toolButtonTargetList.isHidden():
                    self.ui.toolButtonTargetList.click()
                else:
                    self.ui.toolButtonLog.click()
            elif obj is self.ui.toolButtonTargetList and obj.isChecked():
                if not self.ui.toolButtonTypeList.isHidden():
                    self.ui.toolButtonTypeList.click()
                else:
                    self.ui.toolButtonLog.click()
            elif obj is self.ui.toolButtonLog and obj.isChecked():
                if not self.ui.toolButtonTypeList.isHidden():
                    self.ui.toolButtonTypeList.click()
                else:
                    self.ui.toolButtonTargetList.click()

    def updateButtonIcon(self):
        """
        根据文件列表的显示状态更新按钮图标
        """

        if self.ui.widgetFileListPanel.isVisible():
            # 设置按钮图标为“折叠”图标
            self.ui.tBtnCollapse.setIcon(QtGui.QIcon("D:\pycharm_python_project\Annotation-master\wisdom_store\wins\收起列表新.png"))
            self.ui.tBtnCollapse.setToolTip(QtCore.QCoreApplication.translate("Main", "折叠"))
        else:
            # 设置按钮图标为“展开”图标
            self.ui.tBtnCollapse.setIcon(QtGui.QIcon("D:\pycharm_python_project\Annotation-master\wisdom_store\wins\展开列表新.png"))
            self.ui.tBtnCollapse.setToolTip(QtCore.QCoreApplication.translate("Main", "展开"))

    def importNewImage(self, callback=None):
        self.calculateWin.ui.labelCalculateHandleTitle.setText(i18n['data_importing'])
        self.calculateWin.ui.labelTitle.setText(i18n['data_import'])
        self.calculateWin.ui.progressBar.setValue(0)
        self.calculateWin.ui.pBtnOpenResult.setText('确定')
        self.calculateWin.ui.pBtnOpenResult.clicked.disconnect()
        self.calculateWin.ui.pBtnOpenResult.clicked.connect(lambda: self.calculateWin.close())
        self.calculateWin.ui.pBtnOpenResult.setCursor(QtGui.QCursor(Qt.PointingHandCursor))
        self.calculateWin.ui.pBtnOpenResult.hide()
        self.calculateWin.ui.pBtnCancel.hide()
        files, _ = QFileDialog.getOpenFileNames(self, '选择文件', '', '图像文件(*.png *.jpg *.jpeg *.tif *.bmp)')
        if not files:
            return
        else:
            logging.info("[import new Images] {}".format(files))

        self.calculateWin.show()

        conflictFileList = []
        conflictFileNameList = []
        for fileindex, file in enumerate(files):
            filename = os.path.split(file)[-1]
            distpath = os.path.join(self.project.rawDataDir, filename)
            if os.path.exists(distpath):
                conflictFileList.append(file)
                conflictFileNameList.append(filename.split(".")[0])
            else:
                if self.project.needResize():
                    method, size, mode = self.project.getResizeParam()
                    if method == '滑动重叠裁剪':
                        resizeImgs, resizeImgsCoords = sliding_window_crop(file, float(mode), size, size)
                    elif method == '比例缩放':
                        resizeImgs, resizeImgsCoords = resize_image(file, size, size, mode)
                    basename = os.path.basename(file)
                    imgName, imgSuffix  = os.path.splitext(basename)
                    resizeImgNum = len(resizeImgs)
                    resizeStrWidth = len(str(resizeImgNum))
                    for index, rimg in enumerate(resizeImgs):
                        if resizeImgNum > 1:
                            Image.fromarray(rimg).save(os.path.join(self.project.rawDataDir, imgName + "_" + str(index).rjust(resizeStrWidth, '0') + imgSuffix))
                            self.project.addNewRawFiles([imgName + "_" + str(index).rjust(resizeStrWidth, '0') + imgSuffix])
                            self.updateProgressBar((index+1) / resizeImgNum * (fileindex+1) / len(files) * 70)
                        else:
                            Image.fromarray(rimg).save(os.path.join(self.project.rawDataDir, imgName + imgSuffix))
                            self.project.addNewRawFiles([imgName + imgSuffix])
                            self.updateProgressBar((index+1) / resizeImgNum * (fileindex+1) / len(files) * 70)
                else:
                    shutil.copyfile(file, distpath)
                    # self.project.importFiles.append({'path':filename, 'labelCompleted':False})
                    self.project.addNewRawFiles([file])
        if self.project.needResize() and files:
            method, size, mode = self.project.getResizeParam()
            if method == '滑动重叠裁剪':
                if mode == '0.5':
                    alertOk(self, "成功", "导入图片已按1/2比例裁剪至" + str(size) + '*' + str(size))
                elif mode == '0.25':
                    alertOk(self, "成功", "导入图片已按1/4比例裁剪至" + str(size) + '*' + str(size))
                elif mode == '0.0':
                    alertOk(self, "成功", "导入图片已无重叠裁剪至" + str(size) + '*' + str(size))
            elif method == '比例缩放':
                if mode == 'equal':
                    alertOk(self, "成功", "导入图片已等比例缩放至" + str(size) + '*' + str(size))
                elif mode == 'width':
                    alertOk(self, "成功", "导入图片已按横边缩放至" + str(size) + '*' + str(size))
                elif mode == 'height':
                    alertOk(self, "成功", "导入图片已按纵边缩放至" + str(size) + '*' + str(size))

        # 冲突处理
        self.conflictImportResult.clear()
        if len(conflictFileList) != 0:
            for i in range(len(conflictFileList)):
                temp = {}
                temp['labelmeImageFile'] = conflictFileList[i]
                temp['labelmeLabelFile'] = None
                temp['categoryDict'] = None
                self.conflictImportResult.append(temp)

            logging.info("处理导入文件冲突问题...")
            logging.info('冲突文件数量：{}'.format(len(conflictFileList)))
            # logging.info("self.conflictImportResult={}".format(self.conflictImportResult))
            self.importConflictWin = ImportConflictDialog(conflictFileNameList)
            self.importConflictWin.signalConflictProcessByMode.connect(self.processImportConflictByMode)
            self.importConflictWin.signalConflictProcessByUser.connect(self.processImportConflictByUser)
            self.importConflictWin.show()

        self.fileList = copy.deepcopy(self.project.importFiles)
        self.total = len(self.fileList[self.pageSize * (self.currentPage-1) :  self.pageSize * self.currentPage]) + 1
        self.current_num = 0
        for i in range(len(self.fileList)):  # 相对路径转为绝对路径
            self.fileList[i]['path'] = os.path.join(self.project.rawDataDir, self.fileList[i]['path'])
        # Todo:这里fileList跟project中的importFiles是不是重复了

        self.ui.listwidgetFile.clear()
        for file in self.fileList[self.pageSize * (self.currentPage-1) :  self.pageSize * self.currentPage]:
            self.addNewFile(file["path"], file["labelCompleted"], file["inferCompleted"])
            self.current_num += 1
            self.updateProgressBar(70 + self.current_num / self.total * 30)
        self.lastFileIndex = -1
        self.refreshPage(self.currentPage)
        # 无冲突, 更新进度条
        if len(conflictFileList) == 0:
            self.current_num += 1
            self.updateProgressBar(70 + self.current_num / self.total * 30)
        self.updateLabelFileDescription()

        self.project.save()
        self.calculateWin.ui.labelCalculateHandleTitle.setText(i18n['data_import_finished'])
        self.calculateWin.ui.pBtnOpenResult.show()

    def imgReversePhase(self):
        '''
        反相
        '''
        if len(self.project.classes) == 0:
            dlg = Dialog('请先在编辑-设定目标类型中设置标签')
            dlg.exec()
            self.ui.tBtnArrow.click()
            return
        elif len(self.fileList) == 0:
            dlg = Dialog('请先添加图片')
            dlg.exec()
            self.ui.tBtnArrow.click()
            return
        if self.lastFileIndex == -1:
            print('error in imgReversePhase')
            return
        index = self.lastFileIndex
        flag = self.fileList[index]['reversePhase']
        self.fileList[index]['reversePhase'] = not flag
        if len(self.fileList) != len(self.project.importFiles):
            t_file = [file for file in self.project.importFiles if file['path'] in self.fileList[index]['path']][0]
            t_file['reversePhase'] = not flag
        else:
            self.project.importFiles[index]['reversePhase'] = not flag
        self.project.save()
        img_path = self.fileList[index]['path']
        img_name = os.path.basename(img_path)
        save_path = os.path.join(self.project.modifiedImgDir, img_name)
        self.MainGraphicsView.updateReversePhase(save_path=save_path)
        self.lastFileIndex = -1
        self.refreshPage(self.currentPage)
        # self.signalRefreshProject.emit(index)

    def slotpushButtonImagerotation(self):
        if self.labelCheck(mode='rotate'):
            self.birdView.setVisible(False)
            self.myImagerotation = None
            self.myImagerotation = ImageRotationWin(self)
            self.myImagerotation.signal.connect(self.getAngle)
            self.myImagerotation.show()

    def getAngle(self, value):
        index = self.ui.listwidgetFile.currentRow() + self.pageSize * (self.currentPage-1)
        img_path = self.fileList[index]['path']
        img_name = os.path.basename(img_path)
        ori_path = os.path.join(self.project.rawDataDir, img_name)
        en_path = os.path.join(self.project.modifiedImgDir, img_name)
        if os.path.exists(en_path):
            tar_path = en_path
        elif os.path.exists(ori_path):
            tar_path = ori_path
        else:
            alertError(self, "错误", "图像路径不存在", "Error Occurred!")
            return
        self.MainGraphicsView.imageRotate(tar_path, value)
        # self.imgEnhanced()

    def actionRotate(self, flag):
        if self.labelCheck(mode='rotate'):
            self.birdView.setVisible(False)
            if flag == 0:
                angle = 180
            elif flag == 1:
                angle = -90
            elif flag == -1:
                angle = 90
            index = self.ui.listwidgetFile.currentRow() + self.pageSize * (self.currentPage-1)
            img_path = self.fileList[index]['path']
            img_name = os.path.basename(img_path)
            ori_path = os.path.join(self.project.rawDataDir, img_name)
            en_path = os.path.join(self.project.modifiedImgDir, img_name)
            if os.path.exists(en_path):
                tar_path = en_path
            elif os.path.exists(ori_path):
                tar_path = ori_path
            else:
                alertError(self, "错误", "图像路径不存在", "Error Occurred!")
                return
            self.MainGraphicsView.imageRotate(tar_path, angle)
            self.imgEnhanced()

    def getflipcode(self, flipcode):
        if self.labelCheck(mode='rotate'):
            self.birdView.setVisible(False)
            self.MainGraphicsView.imageFlip(flipcode)
            self.imgEnhanced()

    def labelCheck(self, mode = None):
        flag = False
        for label in self.MainGraphicsView.labelList:
            if label.labelClass == "Feedback" or label.labelClass == "RectCut":
                continue
            if label.Die == False:
                flag = True
                break
        if flag and mode:
            if mode == 'rotate':
                alertWarning(self, "警告", "当前图像存在标注，无法旋转，请删除标注后重试", "The current image cannot be rotated due to annotations. Please delete the annotations and try again!")
            elif mode == 'crop':
                alertWarning(self, "警告", "当前图像存在标注，无法裁剪，请删除标注后重试", "The current image cannot be cropped due to annotations. Please delete the annotations and try again!")
            return False
        else:
            return True

    def imgEnhanced(self):
        '''
        原图增强
        '''
        index = self.lastFileIndex
        img_path = self.fileList[index]['path']
        img_name = os.path.basename(img_path)
        save_path = os.path.join(self.project.modifiedImgDir, img_name)
        self.updateListWidgetFile(index)
        self.MainGraphicsView.saveEnhancedImg(save_path=save_path)
        row = self.ui.listwidgetFile.currentRow() + self.pageSize * (self.currentPage-1)
        self.fileList[row]['path'] = save_path

        self.MainGraphicsView.resetBCS()

    def moveBCS(self, brightness, contrast, saturation):
        # 记录最新的调整数据
        if brightness is not None or not hasattr(self, "brightness"):
            self.brightness = brightness
        if contrast is not None or not hasattr(self, "contrast"):
            self.contrast = contrast
        if saturation is not None or not hasattr(self, "saturation"):
            self.saturation = saturation

        if self.enhanceThreadfinished:
            self.enhanceThreadfinished = False
            # if hasattr(self, "enhanceThreadwaiting") and self.enhanceThreadwaiting:
            #     self.enhanceThreadwaiting = False
            args = dict(
                brightness = self.brightness,
                contrast = self.contrast,
                saturation = self.saturation,
            )
            self.brightness = None
            self.contrast = None
            self.saturation = None
            if hasattr(self, "tempThread"):
                self.tempThread.wait()
            self.tempThread = CommonThread(self.MainGraphicsView.updateBCS, args)
            self.tempThread.finished.connect(self.changeState)
            self.tempThread.start()

    def changeState(self):
        self.enhanceThreadfinished = True
        self.MainGraphicsView.microImgItem.setPixmap(self.MainGraphicsView.microImg)
        if self.brightness is not None or self.contrast is not None or self.saturation is not None:
            self.brightnessContrastAdjustmentWin.BCSChanged.emit(self.brightness, self.contrast, self.saturation)
        # if self.brightness:
        #     self.brightnessContrastAdjustmentWin.BrightnessChanged.emit(self.brightness)
        # elif self.contrast:
        #     self.brightnessContrastAdjustmentWin.ContrastChanged.emit(self.contrast)
        # elif self.saturation:
        #     self.brightnessContrastAdjustmentWin.SaturationChanged.emit(self.saturation)

    '''
        文件列表
    '''

    def addNewFile(self, filePath, labelState, inferStatus):
        '''
        向文件列表中添加一项
        '''
        # TODO: 打不开路径报错
        if self.useThumbnail:
            t_pixmap = QPixmap(filePath)
            t_fileItem = Ui_FileItem()
            t_widget = QWidget()
            setattr(t_widget, 'ui', t_fileItem)
            t_fileItem.setupUi(t_widget)
            t_width = 200
            t_pixmap = t_pixmap.scaledToWidth(t_width)
            t_fileItem.labelImage.setPixmap(t_pixmap)
            # t_fileItem.labelImage.raise_()
            # print(os.getcwd())
            # print(t_fileItem.labelImage.width(), t_fileItem.labelImage.height())
            # t_fileItem.labelImage.setText("GGGG")
            filename = os.path.split(filePath)[-1]
            t_fileItem.labelImageName.setText(filename)
            # t_fileItem.tBtnConfirm.setChecked(state)
            # t_fileItem.tBtnConfirm.clicked.connect(lambda: self.confirmLabel(t_fileItem.tBtnConfirm))
            if inferStatus == True:
                t_fileItem.labelStatus.setVisible(True)
                t_fileItem.labelStatus.setPixmap(QtGui.QPixmap(':/resources/已推理-整体.png'))
            elif labelState == True:
                t_fileItem.labelStatus.setVisible(True)
                t_fileItem.labelStatus.setPixmap(QtGui.QPixmap(':/resources/已标注-整体.png'))
            else:
                t_fileItem.labelStatus.setVisible(False)
            t_fileItem.tBtnClose.clicked.connect(lambda: self.deleteImage(t_fileItem.tBtnClose))
            t_listWidget = self.ui.listwidgetFile

            t_item = QListWidgetItem()
            t_item.setSizeHint(QSize(200, 200))

            t_listWidget.addItem(t_item)
            t_listWidget.setItemWidget(t_item, t_widget)
        else:
            t_widget = QWidget()
            filename = os.path.split(filePath)[-1]

            t_layout = QHBoxLayout(t_widget)
            t_layout.setContentsMargins(0, 0, 0, 0)
            t_layout.setSpacing(0)

            t_labelname = QLabel(t_widget)
            t_labelname.setSizePolicy(QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred))
            t_labelname.setMaximumWidth(115)
            t_labelname.setToolTip(filename)
            # sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
            # sizePolicy.setHorizontalStretch(1)
            # sizePolicy.setVerticalStretch(0)
            # sizePolicy.setHeightForWidth(t_labelname.sizePolicy().hasHeightForWidth())
            # t_labelname.setSizePolicy(sizePolicy)
            t_labelname.setAlignment(Qt.AlignLeft|Qt.AlignVCenter)
            t_labelname.setText(filename)
            t_layout.addWidget(t_labelname)

            t_labelstate = QLabel(t_widget)
            # sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
            # sizePolicy.setHorizontalStretch(1)
            # sizePolicy.setVerticalStretch(0)
            # sizePolicy.setHeightForWidth(t_labelstate.sizePolicy().hasHeightForWidth())
            # t_labelstate.setSizePolicy(sizePolicy)
            t_labelstate.setAlignment(Qt.AlignCenter)
            if inferStatus == True:
                t_labelstate.setText('已推理')
                t_labelstate.setStyleSheet("color:#9FA6FF;")
            elif labelState == True:
                t_labelstate.setText('已标注')
                t_labelstate.setStyleSheet("color:#009688;")
            else:
                t_labelstate.setText('未处理')
                t_labelstate.setStyleSheet("color:#8E9FC4;")
            t_labelstate.setObjectName('labelState')
            t_layout.addWidget(t_labelstate)
            # t_layout.setStretchFactor(t_label, 1)

            t_pbtn = QPushButton(t_widget)
            # sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
            # sizePolicy.setHorizontalStretch(1)
            # sizePolicy.setVerticalStretch(0)
            # sizePolicy.setHeightForWidth(t_pbtn.sizePolicy().hasHeightForWidth())
            # t_pbtn.setSizePolicy(sizePolicy)
            t_pbtn.setIcon(QIcon(QPixmap(":/resources/删除-圆圈.png")))
            t_pbtn.setStyleSheet('QPushButton{background: transparent;}')
            t_pbtn.clicked.connect(lambda: self.deleteImage(t_pbtn))
            t_pbtn.setToolTip(QtCore.QCoreApplication.translate("Main", "删除原图或标注"))
            t_layout.addWidget(t_pbtn)
            # t_layout.setStretchFactor(t_pbtn, 1)

            t_layout.setStretchFactor(t_labelname, 2)
            t_layout.setStretchFactor(t_labelstate, 1)
            t_layout.setStretchFactor(t_pbtn, 1)

            t_widget.setStyleSheet("font-family:Microsoft YaHei;font-weight:400;font-size:12px;color:#8E9FC4;")
            t_item = QListWidgetItem()
            t_item.setSizeHint(QSize(200, 40))

            t_listWidget = self.ui.listwidgetFile
            t_listWidget.addItem(t_item)
            t_listWidget.setItemWidget(t_item, t_widget)

    def insertListWidgetFile(self, row, filePath, labelState, inferStatus):
        '''
        向文件列表中插入一项
        '''
        t_pixmap = QPixmap(filePath)
        t_fileItem = Ui_FileItem()
        t_widget = QWidget()
        t_fileItem.setupUi(t_widget)
        t_width = 200
        t_pixmap = t_pixmap.scaledToWidth(t_width)
        t_fileItem.labelImage.setPixmap(t_pixmap)

        filename = os.path.split(filePath)[-1]
        t_fileItem.labelImageName.setText(filename)

        if inferStatus == True:
            t_fileItem.labelStatus.setVisible(True)
            t_fileItem.labelStatus.setPixmap(QtGui.QPixmap(':/resources/已推理-整体.png'))
        elif labelState == True:
            t_fileItem.labelStatus.setVisible(True)
            t_fileItem.labelStatus.setPixmap(QtGui.QPixmap(':/resources/已标注-整体.png'))
        else:
            t_fileItem.labelStatus.setVisible(False)
        t_fileItem.tBtnClose.clicked.connect(lambda: self.deleteImage(t_fileItem.tBtnClose))
        t_listWidget = self.ui.listwidgetFile

        t_item = QListWidgetItem()
        t_item.setSizeHint(QSize(200, 200))
        t_listWidget.insertItem(row, t_item)
        t_listWidget.setItemWidget(t_item, t_widget)

    def updateListWidgetFile(self, index=None):
        '''
        更新文件列表的已标注/已推理状态，index代表只更新第index项
        '''
        lw = self.ui.listwidgetFile
        if index is None:
            for i in range(len(self.fileList)):
                file = self.fileList[i]
                it = lw.item(i)
                if it.listWidget().ui.labelImageName.text() != file["path"]:
                    self.insertListWidgetFile(i, file["path"], file["labelCompleted"], file["inferCompleted"])
        elif index < self.pageSize * (self.currentPage - 1) or index >= self.pageSize * self.currentPage:
            return
        else:
            it = lw.itemWidget(lw.item(index - self.pageSize * (self.currentPage - 1)))
            t_width = 200
            t_pixmap = self.MainGraphicsView.microImg.scaledToWidth(t_width)
            if hasattr(it, 'ui'):
                it.ui.labelImage.setPixmap(t_pixmap)
            file = self.fileList[index]
            if file["inferCompleted"] == True:
                if self.useThumbnail:
                    it.ui.labelStatus.setVisible(True)
                    it.ui.labelStatus.setPixmap(QtGui.QPixmap(':/resources/已推理-整体.png'))
                else:
                    it.findChild(QLabel, 'labelState').setText('已推理')
                    it.findChild(QLabel, 'labelState').setStyleSheet("color:#9FA6FF;")
            elif file["labelCompleted"] == True:
                if self.useThumbnail:
                    it.ui.labelStatus.setVisible(True)
                    it.ui.labelStatus.setPixmap(QtGui.QPixmap(':/resources/已标注-整体.png'))
                else:
                    it.findChild(QLabel, 'labelState').setText('已标注')
                    it.findChild(QLabel, 'labelState').setStyleSheet("color:#009688;")
            else:
                if self.useThumbnail:
                    it.ui.labelStatus.setVisible(False)
                else:
                    it.findChild(QLabel, 'labelState').setText('未处理')
                    it.findChild(QLabel, 'labelState').setStyleSheet("color:#8E9FC4;")

    def confirmLabel(self, fileItem):
        '''
        弃用
        '''
        widget = fileItem.parentWidget().parentWidget()
        modelIndex = self.ui.listwidgetFile.indexAt(QPoint(widget.frameGeometry().x(), widget.frameGeometry().y()))
        orig_state = self.fileList[modelIndex.row()]["labelCompleted"]
        # print(modelIndex.row())
        self.fileList[modelIndex.row()]["labelCompleted"] = not orig_state
        self.project.importFiles[modelIndex.row()]["labelCompleted"] = not orig_state
        self.project.save()

    def deleteImage(self, fileItem):
        # 关闭悬浮
        try:
            self.MainGraphicsView.endHoverTimer()
            self.MainGraphicsView.EfficientvitSAM_instance_clear_point()
        except:
            print("未启动线程")
        if self.useThumbnail:
            widget = fileItem.parentWidget().parentWidget()
        else:
            widget = fileItem.parentWidget()
        modelIndex = self.ui.listwidgetFile.indexAt(QPoint(widget.frameGeometry().x(), widget.frameGeometry().y()))
        self.ui.listwidgetFile.setCurrentRow(modelIndex.row())
        self.showDeleteSelectionWin(modelIndex.row())
        # self.ui.listwidgetFile.setCurrentRow(
        #     modelIndex.row() + 1 if modelIndex.row() + 1 < len(self.fileList) else max(0, modelIndex.row() - 1))
        # del_img = self.fileList.pop(modelIndex.row())
        # print(del_img['path'])
        # os.remove(del_img['path'])
        # print(modelIndex.row())
        # self.project.importFiles.pop(modelIndex.row())
        #
        # self.ui.listwidgetFile.takeItem(modelIndex.row())
        #
        # self.project.save()

    def setLabelCompleted(self, fileName: str):
        '''
        推理完成后将对应状态设为已推理
        '''
        logging.info("[MainWin.setLabelCompleted] 设置{}为推理完成".format(fileName))
        index = self.fileNameList.index(fileName)
        self.fileList[index]['inferCompleted'] = True
        self.MainGraphicsView.inferCompleted = True
        if len(self.fileList) != len(self.project.importFiles):
            t_file = [file for file in self.project.importFiles if file['path'] in self.fileList[index]['path']][0]
            t_file['inferCompleted'] = True
        else:
            self.project.importFiles[index]['inferCompleted'] = True
        self.project.save()
        # 更新文件列表
        self.ui.listwidgetFile.currentRowChanged.disconnect(self.changeFile)
        self.ui.listwidgetFile.clear()
        self.ui.listwidgetFile.currentRowChanged.connect(self.changeFile)
        for file in self.fileList[self.pageSize * (self.currentPage-1) :  self.pageSize * self.currentPage]:
            self.addNewFile(file["path"], file["labelCompleted"], file["inferCompleted"])
        # 推理未确认前标注不可转换
        self.ui.tBtnToPolygonLabel.setEnabled(False)
        self.ui.tBtnToScrawLabel.setEnabled(False)
        self.ui.tBtnFill.setEnabled(False)

    '''
    description: 已标注状态切换
    param {*} self
    return {*}
    '''

    def setCurLabelStatus(self):
        '''
        对当前文件更新已标注/已推理状态
        '''
        labeled = False
        infered = False
        for label in self.MainGraphicsView.labelList:
            if label.labelClass == "Feedback" or label.labelClass == "preseg_scraw" or label.labelClass == "RectCut":
                continue
            if label.Die != True:
                if label.confidence == 1:
                    labeled = True
                else:
                    infered = True
        if self.lastFileIndex != -1:
            index = self.lastFileIndex
            if len(self.fileList) != len(self.project.importFiles):
                t_file = [file for file in self.project.importFiles if file['path'] in self.fileList[index]['path']][0]
            self.fileList[index]['labelCompleted'] = labeled
            # 未处于筛选状态根据index匹配，否则以路径名匹配
            if len(self.fileList) == len(self.project.importFiles):
                self.project.importFiles[index]['labelCompleted'] = labeled
            else:
                t_file['labelCompleted'] = labeled
            print('set labelCompleted:{}'.format(labeled))

            self.fileList[index]['inferCompleted'] = infered
            # 未处于筛选状态根据index匹配，否则以路径名匹配
            if len(self.fileList) == len(self.project.importFiles):
                self.project.importFiles[index]['inferCompleted'] = infered
            else:
                t_file['inferCompleted'] = infered
            self.MainGraphicsView.inferCompleted = infered
            print('set inferCompleted:{}'.format(infered))

            self.project.save()
            # self.ui.listwidgetFile.item(index).
            # self.ui.listwidgetFile.currentRowChanged.disconnect(self.changeFile)
            # self.ui.listwidgetFile.clear()
            # self.ui.listwidgetFile.currentRowChanged.connect(self.changeFile)
            self.updateLabelFileDescription()
            # for file in self.fileList:
            #     self.addNewFile(file["path"], file["labelCompleted"], file["inferCompleted"])
            self.updateListWidgetFile(index)

    def updateLabelFileDescription(self):
        '''
        更新文件列表下方的描述
        '''
        totalnum = len(self.fileList)
        count1 = 0
        count2 = 0
        for file in self.fileList:
            if file['labelCompleted'] == True:
                count1 += 1
            if file['inferCompleted'] == True:
                count2 += 1
        tip = '已标注{}/已推理{}/总数{}'.format(count1, count2, totalnum)
        self.ui.labelFileDescription.setText(tip)

    def savePreSegCache(self, fileIndex):
        if fileIndex != -1:
            self.thresholdSegmentationWin.tableToCache()
            preSegCache = self.thresholdSegmentationWin.getCache()
            self.preSegCache[fileIndex] = preSegCache

    def loadPreSegCache(self, fileIndex):
        if fileIndex in self.preSegCache:
            self.thresholdSegmentationWin.setCache(self.preSegCache[fileIndex])
        else:
            self.thresholdSegmentationWin.setCache()
        if self.ui.pushButtonSegmentation.isChecked() and self.thresholdSegmentationWin.ui.toolButtonFold.isChecked():
            self.thresholdSegmentationWin.show()

    def keeplabel(self, conflictmode):
        labelList = self.MainGraphicsView.getLabelList()
        if conflictmode == ConflictMode.Replace:
            for tarLabel in labelList:
                self.subLabelNum(tarLabel.type, tarLabel.labelClass)
                tarLabel.Die = True
                tarLabel.setVisible(False)
                del tarLabel
            labelList.clear()
            # for i in range(len(labelList)-1, -1, -1):
            #     if self.MainGraphicsView.allowScraw and labelList[i].labelClass == "Scraw":
            #         labelList[i].Die = True
            #         labelList[i].setVisible(False)
            #         del labelList[i]
            #         labelList.remove(labelList[i])
            for srcLabel in self.labelKeepboard:
                t_label = None
                t_type = srcLabel["label_type"]
                if t_type == None:
                    continue
                t_operator = srcLabel["operator"]
                t_confidence = srcLabel["confidence"]
                if srcLabel["label_class"] == "Rectangle":
                    t_rect = QRectF(srcLabel["left"], srcLabel["top"], srcLabel["width"], srcLabel["height"])
                    t_label = RectLabel(
                        t_rect,
                        self.MainGraphicsView.mapToScene(self.MainGraphicsView.rect()).boundingRect(),
                        self.MainGraphicsView.microImgRectF(),
                        QColor(255, 255, 255),
                        QColor(self.project.getColorByType(t_type)),
                        t_type,
                        t_operator,
                        t_confidence
                    )
                    t_label.creating = False
                elif srcLabel["label_class"] == "Polygon":
                    point_list = []
                    for point in srcLabel["point_list"]:
                        point_list.append(QPoint(*point))
                    t_label = PolygonCurveLabel(
                        QPolygonF(point_list),
                        None,
                        None,
                        self.MainGraphicsView.mapToScene(self.MainGraphicsView.rect()).boundingRect(),
                        self.MainGraphicsView.microImgRectF(),
                        QColor(255, 255, 255),
                        QColor(self.project.getColorByType(t_type)),
                        t_type,
                        t_operator,
                        t_confidence
                    )
                    t_label.creating = False
                elif srcLabel["label_class"] == "PolygonCurve":
                    plg_points, pre_points, nex_points = srcLabel["point_list"]
                    for i in range(len(plg_points)):
                        plg_points[i] = QPoint(*plg_points[i])
                        pre_points[i] = QPoint(*pre_points[i])
                        nex_points[i] = QPoint(*nex_points[i])
                    t_label = PolygonCurveLabel(
                        QPolygonF(plg_points),
                        QPolygonF(pre_points),
                        QPolygonF(nex_points),
                        self.MainGraphicsView.mapToScene(self.MainGraphicsView.rect()).boundingRect(),
                        self.MainGraphicsView.microImgRectF(),
                        QColor(255, 255, 255),
                        QColor(self.project.getColorByType(t_type)),
                        t_type,
                        t_operator,
                        t_confidence
                    )
                    t_label.creating = False
                elif srcLabel["label_class"] == "Line":
                    point_list = []
                    for point in srcLabel["point_list"]:
                        point_list.append(QPoint(*point))
                    t_label = LineLabel(
                        QPolygonF(point_list),
                        self.MainGraphicsView.mapToScene(self.MainGraphicsView.rect()).boundingRect(),
                        self.MainGraphicsView.microImgRectF(),
                        QColor(255, 255, 255),
                        QColor(self.project.getColorByType(t_type)),
                        t_type,
                        t_operator,
                        t_confidence
                    )
                    t_label.creating = False
                elif srcLabel["label_class"] == "Scraw":
                    byteArray = base64.b64decode(srcLabel["label_png"])
                    pixmap = QPixmap()
                    pixmap.loadFromData(byteArray, "png")
                    if "conf_map" in srcLabel.keys():
                        confmap = base64ToNumpyUint8(srcLabel["conf_map"])
                    else:
                        confmap = None
                    oriLabel = self.MainGraphicsView.getLabel(t_type, 'Scraw')
                    if oriLabel is not None:
                        oripixmap = oriLabel.getPixmap()
                        orinpy = imgPixmapToNmp(oripixmap)
                        srcnpy = imgPixmapToNmp(pixmap)
                        # for i in range(len(srcnpy)):
                        #     for j in range(len(srcnpy[0])):
                        #         if list(srcnpy[i][j]) != [0,0,0,0]:
                        #             orinpy[i][j] = srcnpy[i][j]
                        newnpy = np.logical_or(np.any(orinpy != [0,0,0,0], axis=2), np.any(srcnpy != [0,0,0,0], axis=2))
                        if np.any(newnpy):
                            im = Image.fromarray(newnpy)
                            im = im.convert('RGBA')
                            newPixmap = im.toqpixmap()
                            oriLabel.setPixmap(newPixmap)
                            oriLabel.updateColor()
                            oriLabel.updateAlpha(self.MainGraphicsView.alpha)
                            oriLabel.updateAlphaSelect(self.MainGraphicsView.alphaSelect)
                    else:
                        t_label = ScrawLabel(
                            pixmap,
                            confmap,
                            self.MainGraphicsView.microImg,
                            QColor(255, 255, 255),
                            QColor(self.project.getColorByType(t_type)),
                            t_type,
                            t_operator,
                            t_confidence
                        )
                        t_label.penWidth = self.MainGraphicsView.scrawCursor.cursorWidth
                        t_label.creating = False
                elif srcLabel["label_class"] == "Point":
                    t_point = QPointF(*srcLabel["point"])
                    t_label = PointLabel(
                        t_point,
                        self.MainGraphicsView.mapToScene(self.MainGraphicsView.rect()).boundingRect(),
                        self.MainGraphicsView.microImgRectF(),
                        QColor(255, 255, 255),
                        QColor(self.project.getColorByType(t_type)),
                        t_type,
                        t_operator,
                        t_confidence
                    )
                    t_label.creating = False
                elif srcLabel["label_class"] == "Tag":
                    t_point = QPointF(*srcLabel["point"])
                    t_label = TagLabel(
                        t_point,
                        self.MainGraphicsView.mapToScene(self.MainGraphicsView.rect()).boundingRect(),
                        self.MainGraphicsView.microImgRectF(),
                        QColor(255, 255, 255),
                        QColor(self.project.getColorByType(t_type)),
                        t_type,
                        t_operator,
                        t_confidence
                    )
                    t_label.creating = False
                elif srcLabel["label_class"] == "Circle":
                    t_center = QPointF(*srcLabel["center"])
                    t_rx, t_ry = srcLabel["radius"]
                    t_label = CircleLabel(
                        (t_center, t_rx, t_ry),
                        self.MainGraphicsView.mapToScene(self.MainGraphicsView.rect()).boundingRect(),
                        self.MainGraphicsView.microImgRectF(),
                        QColor(255, 255, 255),
                        QColor(self.project.getColorByType(t_type)),
                        t_type,
                        t_operator,
                        t_confidence
                    )
                    t_label.creating = False
                else:
                    pass
                if t_label != None:
                    self.addLabelNum(t_label.type, t_label.labelClass)
                    self.MainGraphicsView.loadLabel(t_label)
            self.MainGraphicsView.changeScrawMode(False)
            if self.MainGraphicsView.allowScraw:
                self.updateToolBtnSlot()
        elif conflictmode == ConflictMode.Coexist:
            for srcLabel in self.labelKeepboard:
                t_label = None
                t_type = srcLabel["label_type"]
                if t_type == None:
                    continue
                t_operator = srcLabel["operator"]
                t_confidence = srcLabel["confidence"]
                if srcLabel["label_class"] == "Rectangle":
                    t_rect = QRectF(srcLabel["left"], srcLabel["top"], srcLabel["width"], srcLabel["height"])
                    t_label = RectLabel(
                        t_rect,
                        self.MainGraphicsView.mapToScene(self.MainGraphicsView.rect()).boundingRect(),
                        self.MainGraphicsView.microImgRectF(),
                        QColor(255, 255, 255),
                        QColor(self.project.getColorByType(t_type)),
                        t_type,
                        t_operator,
                        t_confidence
                    )
                    t_label.creating = False
                elif srcLabel["label_class"] == "Polygon":
                    point_list = []
                    for point in srcLabel["point_list"]:
                        point_list.append(QPoint(*point))
                    t_label = PolygonCurveLabel(
                        QPolygonF(point_list),
                        None,
                        None,
                        self.MainGraphicsView.mapToScene(self.MainGraphicsView.rect()).boundingRect(),
                        self.MainGraphicsView.microImgRectF(),
                        QColor(255, 255, 255),
                        QColor(self.project.getColorByType(t_type)),
                        t_type,
                        t_operator,
                        t_confidence
                    )
                    t_label.creating = False
                elif srcLabel["label_class"] == "PolygonCurve":
                    plg_points, pre_points, nex_points = srcLabel["point_list"]
                    for i in range(len(plg_points)):
                        plg_points[i] = QPoint(*plg_points[i])
                        pre_points[i] = QPoint(*pre_points[i])
                        nex_points[i] = QPoint(*nex_points[i])
                    t_label = PolygonCurveLabel(
                        QPolygonF(plg_points),
                        QPolygonF(pre_points),
                        QPolygonF(nex_points),
                        self.MainGraphicsView.mapToScene(self.MainGraphicsView.rect()).boundingRect(),
                        self.MainGraphicsView.microImgRectF(),
                        QColor(255, 255, 255),
                        QColor(self.project.getColorByType(t_type)),
                        t_type,
                        t_operator,
                        t_confidence
                    )
                    t_label.creating = False
                elif srcLabel["label_class"] == "Line":
                    point_list = []
                    for point in srcLabel["point_list"]:
                        point_list.append(QPoint(*point))
                    t_label = LineLabel(
                        QPolygonF(point_list),
                        self.MainGraphicsView.mapToScene(self.MainGraphicsView.rect()).boundingRect(),
                        self.MainGraphicsView.microImgRectF(),
                        QColor(255, 255, 255),
                        QColor(self.project.getColorByType(t_type)),
                        t_type,
                        t_operator,
                        t_confidence
                    )
                    t_label.creating = False
                elif srcLabel["label_class"] == "Scraw":
                    byteArray = base64.b64decode(srcLabel["label_png"])
                    pixmap = QPixmap()
                    pixmap.loadFromData(byteArray, "png")
                    if "conf_map" in srcLabel.keys():
                        confmap = base64ToNumpyUint8(srcLabel["conf_map"])
                    else:
                        confmap = None
                    oriLabel = self.MainGraphicsView.getLabel(t_type, 'Scraw')
                    if oriLabel is not None:
                        oripixmap = oriLabel.getPixmap()
                        orinpy = imgPixmapToNmp(oripixmap)
                        srcnpy = imgPixmapToNmp(pixmap)
                        # for i in range(len(srcnpy)):
                        #     for j in range(len(srcnpy[0])):
                        #         if list(srcnpy[i][j]) != [0,0,0,0]:
                        #             orinpy[i][j] = srcnpy[i][j]
                        newnpy = np.logical_or(np.any(orinpy != [0,0,0,0], axis=2), np.any(srcnpy != [0,0,0,0], axis=2))
                        if np.any(newnpy):
                            im = Image.fromarray(newnpy)
                            im = im.convert('RGBA')
                            newPixmap = im.toqpixmap()
                            oriLabel.setPixmap(newPixmap)
                            oriLabel.updateColor()
                            oriLabel.updateAlpha(self.MainGraphicsView.alpha)
                            oriLabel.updateAlphaSelect(self.MainGraphicsView.alphaSelect)
                    else:
                        t_label = ScrawLabel(
                            pixmap,
                            confmap,
                            self.MainGraphicsView.microImg,
                            QColor(255, 255, 255),
                            QColor(self.project.getColorByType(t_type)),
                            t_type,
                            t_operator,
                            t_confidence
                        )
                        t_label.penWidth = self.MainGraphicsView.scrawCursor.cursorWidth
                        t_label.creating = False
                elif srcLabel["label_class"] == "Point":
                    t_point = QPointF(*srcLabel["point"])
                    t_label = PointLabel(
                        t_point,
                        self.MainGraphicsView.mapToScene(self.MainGraphicsView.rect()).boundingRect(),
                        self.MainGraphicsView.microImgRectF(),
                        QColor(255, 255, 255),
                        QColor(self.project.getColorByType(t_type)),
                        t_type,
                        t_operator,
                        t_confidence
                    )
                    t_label.creating = False
                elif srcLabel["label_class"] == "Tag":
                    t_point = QPointF(*srcLabel["point"])
                    t_label = TagLabel(
                        t_point,
                        self.MainGraphicsView.mapToScene(self.MainGraphicsView.rect()).boundingRect(),
                        self.MainGraphicsView.microImgRectF(),
                        QColor(255, 255, 255),
                        QColor(self.project.getColorByType(t_type)),
                        t_type,
                        t_operator,
                        t_confidence
                    )
                    t_label.creating = False
                elif srcLabel["label_class"] == "Circle":
                    t_center = QPointF(*srcLabel["center"])
                    t_rx, t_ry = srcLabel["radius"]
                    t_label = CircleLabel(
                        (t_center, t_rx, t_ry),
                        self.MainGraphicsView.mapToScene(self.MainGraphicsView.rect()).boundingRect(),
                        self.MainGraphicsView.microImgRectF(),
                        QColor(255, 255, 255),
                        QColor(self.project.getColorByType(t_type)),
                        t_type,
                        t_operator,
                        t_confidence
                    )
                    t_label.creating = False
                else:
                    pass
                if t_label != None:
                    self.addLabelNum(t_label.type, t_label.labelClass)
                    self.MainGraphicsView.loadLabel(t_label)
        elif conflictmode == ConflictMode.Skip:
            self.labelKeepboard.clear()
        else:
            self.labelKeepboard.clear()
        self.setTargetSideBar()
        self.setTypeSideBar()
        self.setCurLabelStatus()  # 确认当前图像已标注状态

    def copylabel(self):
        if hasattr(self.MainGraphicsView, "multiplechoicelist") and self.MainGraphicsView.multiplechoicelist:
            labelList = self.MainGraphicsView.multiplechoicelist
            polygonLabels = []
            for x in range(0, len(labelList)):
                    temp_Export = labelList[x].getExport()
                    temp_Export["label_type"] = self.project.getIdByType(temp_Export["label_type"])
                    polygonLabels.append(temp_Export)
                    self.labelClipboard = polygonLabels
        else:
            labelList = self.MainGraphicsView.getLabelList()
            polygonLabels = []
            for x in range(0, len(labelList)):
                if labelList[x].isSelected() == 1:
                    temp_Export = labelList[x].getExport()
                    temp_Export["label_type"] = self.project.getIdByType(temp_Export["label_type"])
                    polygonLabels.append(temp_Export)
                    self.labelClipboard = polygonLabels

    def pastelabel(self):
        row = self.ui.listwidgetFile.currentRow() + self.pageSize * (self.currentPage - 1)
        fileList = self.fileList
        if len(fileList) == 0:
            return
        self.filepath = fileList[self.lastFileIndex].get('path')
        self.filepath2 = fileList[row].get('path')
        self.save(fileList[row].get('path'))
        # 读取路径
        filepath = self.filepath
        filepath2 = self.filepath2
        filedir, tempfilename = os.path.split(filepath)
        shotname, extension = os.path.splitext(tempfilename)
        distpath = os.path.join(self.project.labeledDataDir, shotname + ".json")
        # 保存路径
        filedir2, tempfilename2 = os.path.split(filepath2)
        shotname2, extension2 = os.path.splitext(tempfilename2)
        distpath2 = os.path.join(self.project.labeledDataDir, shotname2 + ".json")

        rawImage = Image.open(filepath)
        imgHeight = rawImage.height
        imgWidth = rawImage.width

        dict = {}
        dict["version"] = self.config.version
        dict["file_path"] = filepath
        dict["classification"] = [_class["id"] for _class in self.project.classes]
        # dict["classificationColor"] = [dict(_class["type"], _class["color"]) for _class in self.project.classes]

        dict["image_height"] = imgHeight
        dict["image_width"] = imgWidth
        polygonLabels = []

        dict["image_object_detection"] = polygonLabels

        with open(os.path.join(self.project.labeledDataDir, distpath2), 'r', encoding='utf-8') as f:
            x = json.load(f)
            dict["image_object_detection"] = self.labelClipboard + x["image_object_detection"]

        with open(os.path.join(self.project.labeledDataDir, distpath2), 'w', encoding='utf-8') as file_obj:
            json.dump(dict, file_obj, indent=4, ensure_ascii=False)

        self.MainGraphicsView.clearlabel()

        path = filepath2
        # TODO: 加载标注文件，更新base中的数值，通知sidebar
        filedir, tempfilename = os.path.split(path)
        shotname, extension = os.path.splitext(tempfilename)

        label_path = os.path.join(self.project.labeledDataDir, shotname + ".json")

        if os.path.isfile(label_path):
            with open(label_path, 'r', encoding='utf-8') as file_obj:
                dict = json.load(file_obj)
                # TODO: 版本不一致应该警告
                if dict["version"] != self.config.version:
                    pass

                # for type in dict["classification"]:
                #     if type not in self.project.getTypes():
                #         self.project.addNewClass(type, dict["classificationColor"][type])

                for label in dict["image_object_detection"]:
                    t_label = None
                    t_type = self.project.getTypeById(label["label_type"])
                    if t_type == None:
                        continue
                    t_operator = label["operator"]
                    t_confidence = label["confidence"]
                    if label["label_class"] == "Rectangle":
                        t_rect = QRectF(label["left"], label["top"], label["width"], label["height"])
                        t_label = RectLabel(
                            t_rect,
                            self.MainGraphicsView.mapToScene(self.MainGraphicsView.rect()).boundingRect(),
                            self.MainGraphicsView.microImgRectF(),
                            QColor(255, 255, 255),
                            QColor(self.project.getColorByType(t_type)),
                            t_type,
                            t_operator,
                            t_confidence
                        )
                        t_label.creating = False
                    elif label["label_class"] == "Polygon":
                        point_list = []
                        for point in label["point_list"]:
                            point_list.append(QPoint(*point))
                        t_label = PolygonCurveLabel(
                            QPolygonF(point_list),
                            None,
                            None,
                            self.MainGraphicsView.mapToScene(self.MainGraphicsView.rect()).boundingRect(),
                            self.MainGraphicsView.microImgRectF(),
                            QColor(255, 255, 255),
                            QColor(self.project.getColorByType(t_type)),
                            t_type,
                            t_operator,
                            t_confidence
                        )
                        t_label.creating = False
                    elif label["label_class"] == "PolygonCurve":
                        plg_points, pre_points, nex_points = label["point_list"]
                        for i in range(len(plg_points)):
                            plg_points[i] = QPoint(*plg_points[i])
                            pre_points[i] = QPoint(*pre_points[i])
                            nex_points[i] = QPoint(*nex_points[i])
                        t_label = PolygonCurveLabel(
                            QPolygonF(plg_points),
                            QPolygonF(pre_points),
                            QPolygonF(nex_points),
                            self.MainGraphicsView.mapToScene(self.MainGraphicsView.rect()).boundingRect(),
                            self.MainGraphicsView.microImgRectF(),
                            QColor(255, 255, 255),
                            QColor(self.project.getColorByType(t_type)),
                            t_type,
                            t_operator,
                            t_confidence
                        )
                        t_label.creating = False
                    elif label["label_class"] == "Line":
                        point_list = []
                        for point in label["point_list"]:
                            point_list.append(QPoint(*point))
                        t_label = LineLabel(
                            QPolygonF(point_list),
                            self.MainGraphicsView.mapToScene(self.MainGraphicsView.rect()).boundingRect(),
                            self.MainGraphicsView.microImgRectF(),
                            QColor(255, 255, 255),
                            QColor(self.project.getColorByType(t_type)),
                            t_type,
                            t_operator,
                            t_confidence
                        )
                        t_label.creating = False
                    elif label["label_class"] == "Scraw":
                        byteArray = base64.b64decode(label["label_png"])
                        pixmap = QPixmap()
                        pixmap.loadFromData(byteArray, "png")
                        if "conf_map" in label.keys():
                            confmap = base64ToNumpyUint8(label["conf_map"])
                        else:
                            confmap = None
                        t_label = ScrawLabel(
                            pixmap,
                            confmap,
                            self.MainGraphicsView.microImg,
                            QColor(255, 255, 255),
                            QColor(self.project.getColorByType(t_type)),
                            t_type,
                            t_operator,
                            t_confidence
                        )
                        t_label.penWidth = self.MainGraphicsView.scrawCursor.cursorWidth
                        t_label.creating = False
                    elif label["label_class"] == "Point":
                        t_point = QPointF(*label["point"])
                        t_label = PointLabel(
                            t_point,
                            self.MainGraphicsView.mapToScene(self.MainGraphicsView.rect()).boundingRect(),
                            self.MainGraphicsView.microImgRectF(),
                            QColor(255, 255, 255),
                            QColor(self.project.getColorByType(t_type)),
                            t_type,
                            t_operator,
                            t_confidence
                        )
                        t_label.creating = False
                    elif label["label_class"] == "Tag":
                        t_point = QPointF(*label["point"])
                        t_label = TagLabel(
                            t_point,
                            self.MainGraphicsView.mapToScene(self.MainGraphicsView.rect()).boundingRect(),
                            self.MainGraphicsView.microImgRectF(),
                            QColor(255, 255, 255),
                            QColor(self.project.getColorByType(t_type)),
                            t_type,
                            t_operator,
                            t_confidence
                        )
                        t_label.creating = False
                    elif label["label_class"] == "Circle":
                        t_center = QPointF(*label["center"])
                        t_rx, t_ry = label["radius"]
                        t_label = CircleLabel(
                            (t_center, t_rx, t_ry),
                            self.MainGraphicsView.mapToScene(self.MainGraphicsView.rect()).boundingRect(),
                            self.MainGraphicsView.microImgRectF(),
                            QColor(255, 255, 255),
                            QColor(self.project.getColorByType(t_type)),
                            t_type,
                            t_operator,
                            t_confidence
                        )
                        t_label.creating = False
                    else:
                        pass
                    self.addLabelNum(t_label.type, t_label.labelClass)
                    self.MainGraphicsView.loadLabel(t_label)
        self.changeFile(row)

    def bridge(self):
        if hasattr(self, "labelClipboard"):
            self.signal2.emit()

    def ctrl_event(self, event):
        if event.event_type == keyboard.KEY_DOWN and event.name == 'ctrl' and self.ctrl_state == 0:
            self.ctrl_state = 1
        elif event.event_type == keyboard.KEY_UP and event.name == 'ctrl':
            self.ctrl_state = 0
    '''
    description: 切换文件，读取新标注
    param {*} self
    param {*} row
    return {*}
    '''

    def changeFile(self, row):
        '''
        点击文件列表后，切换当前图像与标注
        '''
        # 切图时暂停智能分割重新加载图片后继续
        if self.MainGraphicsView.allowAIMagic:
            self.MainGraphicsView.endHoverTimer()
            self.MainGraphicsView.efficientvitSAM_enable = False

        row = row + self.pageSize * (self.currentPage - 1)
        # 记录图像大小及尺寸
        lastFileWidth = self.MainGraphicsView.microImg.width()
        lastFileHeight = self.MainGraphicsView.microImg.height()
        lastScale = self.MainGraphicsView._scale
        lastCenter = self.MainGraphicsView.mapToScene(self.MainGraphicsView.viewport().rect().center()) / lastScale
        if self.lastFileIndex != -1:
            boolLastFileInfer = self.fileList[self.lastFileIndex]['inferCompleted']# 记录上一张是否为已预测
            boolCurrentFileInfer = self.fileList[row]['inferCompleted']# 记录当前是否为已预测
        # 判断上一张是否为预分割
        labelList = self.MainGraphicsView.getLabelList()
        boolLastFilePreseg = False
        for _label in labelList:
            if _label.labelClass == 'preseg_scraw' and _label.Die == False:
                boolLastFilePreseg = True
                break
        self.MainGraphicsView.inferCompleted = False
        # 已标注的标注可转换，已推理未确认的标注不可转换
        if 0 < row < len(self.fileList) and self.fileList[row]['labelCompleted']:
            self.MainGraphicsView.inferCompleted = False
            self.ui.tBtnToPolygonLabel.setEnabled(True)
            self.ui.tBtnToScrawLabel.setEnabled(True)
            self.ui.tBtnFill.setEnabled(True)
        if 0 < row < len(self.fileList) and self.fileList[row]['inferCompleted']:
            self.MainGraphicsView.inferCompleted = True
            self.ui.tBtnToPolygonLabel.setEnabled(False)
            self.ui.tBtnToScrawLabel.setEnabled(False)
            self.ui.tBtnFill.setEnabled(False)
        fileList = self.fileList
        if self.lastFileIndex != -1 and fileList:   #cj
            self.savePreSegCache(self.lastFileIndex)
            self.save(fileList[self.lastFileIndex].get('path'))
        self.setCurLabelStatus()    # 确认当前图像已标注状态
        self.lastFileIndex = row
        if row < 0 or row >= len(fileList):
            return False
        reversed_flag = fileList[row].get('reversePhase')
        if reversed_flag:
            self.actionReversed.setChecked(reversed_flag)
        else:
            self.actionReversed.setChecked(False)  # 兼容旧版本项目

        self.labelKeepboard.clear()
        self.labelKeepboard.extend([lastFileLabel.getExport() for lastFileLabel in self.MainGraphicsView.getLabelList()])

        path = fileList[row].get('path')

        # TODO: 加载标注文件，更新base中的数值，通知sidebar
        filedir, tempfilename = os.path.split(path)
        shotname, extension = os.path.splitext(tempfilename)

        label_path = os.path.join(self.project.labeledDataDir, shotname + ".json")
        # 处理增强图像
        modified_img = os.path.join(self.project.modifiedImgDir, tempfilename)
        if os.path.exists(modified_img):
            self.MainGraphicsView.openNewImage(modified_img)
            self.birdView.openNewImage(modified_img)
        else:
            self.MainGraphicsView.openNewImage(path)
            self.birdView.openNewImage(path)
        self.MainGraphicsView.updateBirdView()
        self.MainGraphicsView.scrawCursor.cursorWidth = self.ui.horizontalSliderBrushSize.value()

        if os.path.isfile(label_path):
            with open(label_path, 'r', encoding='utf-8') as file_obj:
                dict = json.load(file_obj)
                # TODO: 版本不一致应该警告
                if dict["version"] != self.config.version:
                    pass

                # for type in dict["classification"]:
                #     if type not in self.project.getTypes():
                #         self.project.addNewClass(type, dict["classificationColor"][type])

                for label in dict["image_object_detection"]:
                    t_label = None
                    t_type = self.project.getTypeById(label["label_type"])
                    if t_type == None:
                        continue
                    t_operator = label["operator"]
                    t_confidence = label["confidence"]
                    if label["label_class"] == "Rectangle":
                        t_rect = QRectF(label["left"], label["top"], label["width"], label["height"])
                        t_label = RectLabel(
                            t_rect,
                            self.MainGraphicsView.mapToScene(self.MainGraphicsView.rect()).boundingRect(),
                            self.MainGraphicsView.microImgRectF(),
                            QColor(255, 255, 255),
                            QColor(self.project.getColorByType(t_type)),
                            t_type,
                            t_operator,
                            t_confidence
                        )
                        t_label.creating = False
                    elif label["label_class"] == "Polygon":
                        point_list = []
                        for point in label["point_list"]:
                            point_list.append(QPoint(*point))
                        t_label = PolygonCurveLabel(
                            QPolygonF(point_list),
                            None,
                            None,
                            self.MainGraphicsView.mapToScene(self.MainGraphicsView.rect()).boundingRect(),
                            self.MainGraphicsView.microImgRectF(),
                            QColor(255, 255, 255),
                            QColor(self.project.getColorByType(t_type)),
                            t_type,
                            t_operator,
                            t_confidence
                        )
                        t_label.creating = False
                    elif label["label_class"] == "PolygonCurve":
                        plg_points, pre_points, nex_points = label["point_list"]
                        for i in range(len(plg_points)):
                            plg_points[i] = QPoint(*plg_points[i])
                            pre_points[i] = QPoint(*pre_points[i])
                            nex_points[i] = QPoint(*nex_points[i])
                        t_label = PolygonCurveLabel(
                            QPolygonF(plg_points),
                            QPolygonF(pre_points),
                            QPolygonF(nex_points),
                            self.MainGraphicsView.mapToScene(self.MainGraphicsView.rect()).boundingRect(),
                            self.MainGraphicsView.microImgRectF(),
                            QColor(255, 255, 255),
                            QColor(self.project.getColorByType(t_type)),
                            t_type,
                            t_operator,
                            t_confidence
                        )
                        t_label.creating = False
                    elif label["label_class"] == "Line":
                        point_list = []
                        for point in label["point_list"]:
                            point_list.append(QPoint(*point))
                        t_label = LineLabel(
                            QPolygonF(point_list),
                            self.MainGraphicsView.mapToScene(self.MainGraphicsView.rect()).boundingRect(),
                            self.MainGraphicsView.microImgRectF(),
                            QColor(255, 255, 255),
                            QColor(self.project.getColorByType(t_type)),
                            t_type,
                            t_operator,
                            t_confidence
                        )
                        t_label.creating = False
                    elif label["label_class"] == "Scraw":
                        byteArray = base64.b64decode(label["label_png"])
                        pixmap = QPixmap()
                        pixmap.loadFromData(byteArray, "png")
                        if "conf_map" in label.keys():
                            confmap = base64ToNumpyUint8(label["conf_map"])
                        else:
                            confmap = None
                        t_label = ScrawLabel(
                            pixmap,
                            confmap,
                            self.MainGraphicsView.microImg,
                            QColor(255, 255, 255),
                            QColor(self.project.getColorByType(t_type)),
                            t_type,
                            t_operator,
                            t_confidence
                        )
                        t_label.penWidth = self.MainGraphicsView.scrawCursor.cursorWidth
                        t_label.creating = False
                    elif label["label_class"] == "Point":
                        t_point = QPointF(*label["point"])
                        t_label = PointLabel(
                            t_point,
                            self.MainGraphicsView.mapToScene(self.MainGraphicsView.rect()).boundingRect(),
                            self.MainGraphicsView.microImgRectF(),
                            QColor(255, 255, 255),
                            QColor(self.project.getColorByType(t_type)),
                            t_type,
                            t_operator,
                            t_confidence
                        )
                        t_label.creating = False
                    elif label["label_class"] == "Tag":
                        t_point = QPointF(*label["point"])
                        t_label = TagLabel(
                            t_point,
                            self.MainGraphicsView.mapToScene(self.MainGraphicsView.rect()).boundingRect(),
                            self.MainGraphicsView.microImgRectF(),
                            QColor(255, 255, 255),
                            QColor(self.project.getColorByType(t_type)),
                            t_type,
                            t_operator,
                            t_confidence
                        )
                        t_label.creating = False
                    elif label["label_class"] == "Circle":
                        t_center = QPointF(*label["center"])
                        t_rx, t_ry = label["radius"]
                        t_label = CircleLabel(
                            (t_center, t_rx, t_ry),
                            self.MainGraphicsView.mapToScene(self.MainGraphicsView.rect()).boundingRect(),
                            self.MainGraphicsView.microImgRectF(),
                            QColor(255, 255, 255),
                            QColor(self.project.getColorByType(t_type)),
                            t_type,
                            t_operator,
                            t_confidence
                        )
                        t_label.creating = False
                    else:
                        pass
                    if t_label != None:
                        self.MainGraphicsView.loadLabel(t_label)
            self.MainGraphicsView.changeScrawMode(False)
            self.MainGraphicsView.changeAlpha(self.project.labelAlpha)
            self.MainGraphicsView.changeAlphaSelect(self.project.labelAlphaSelect)
            self.MainGraphicsView.setScale(int(self.ui.comboBoxZoomValue.currentText().replace("%", "")) / 100)
            self.clearUndoStack()

        self.MainGraphicsView.viewport().adjustSize()
        self.MainGraphicsView.fitScreen()

        self.switchWidgetThreshold()

        self.setTargetSideBar()
        self.setTypeSideBar()
        # if self.ui.tBtnBrush.isChecked():
        #     self.slotTBtnBrush()
        self.MainGraphicsView.set_current_img()
        # self.ui.tBtnHand.click()
        # self.CurrentFileChanged.emit(path)
        # 切图后重置智能分割相关参数
        # self.MainGraphicsView.set_current_img()
        if self.MainGraphicsView.allowAIMagic:
            # self.MainGraphicsView.load_efficientvitSAM()
            self.ui.tBtnHand.setChecked(True)
            self.slotTBtnHand()
            self.MainGraphicsView.EfficientvitSAM_instance_clear_point()
        # 加载预分割缓存
        if self.ui.widgetSegmentation.isVisible():
            self.loadPreSegCache(row)
        self.updateToolBtnSlot()
        if self.brightnessContrastAdjustmentWin.ui.toolButtonFold.isChecked():
            self.brightnessContrastAdjustmentWin.ui.toolButtonFold.setChecked(False)
            self.brightnessContrastAdjustmentWin.trans()
        if self.histogramAdjustmentWin.ui.toolButtonFold.isChecked():
            self.histogramAdjustmentWin.ui.toolButtonFold.setChecked(False)
            self.histogramAdjustmentWin.trans()
        #1修改，此处要添加ProcessingWidget的可见性
        if self.labelShowWin.ui.toolButtonFold.isChecked():
            self.labelShowWin.ui.toolButtonFold.setChecked(False)
            self.labelShowWin.trans()
        if self.morphologyWin.ui.toolButtonFold.isChecked():
            self.morphologyWin.ui.toolButtonFold.setChecked(False)
            self.morphologyWin.ui.trans()

        # 保留上一张标注冲突(图像大小不一致或已有标注)
        if self.action_keep_label.isChecked():
            # 判断当前图是否为预分割
            labelList = self.MainGraphicsView.getLabelList()
            boolCurrentFilePreseg = False
            for _label in labelList:
                if _label.labelClass == 'pregseg_scraw' and _label.Die == False:
                    boolCurrentFilePreseg = True
                    break
            # 对于已预测图片和预分割图片，既不传递标注，也不保留上一张标注
            if not boolLastFileInfer and not boolCurrentFileInfer and not boolLastFilePreseg and not boolCurrentFilePreseg and len(self.labelKeepboard) != 0:
                if self.MainGraphicsView.microImg.width() != lastFileWidth or self.MainGraphicsView.microImg.height() != lastFileHeight:
                    alertWarning(self, "警告", "图像大小不匹配，无法保留上一张标注", "The image size does not match and the previous annotation cannot be retained!")
                    self.keeplabel(ConflictMode.Skip)
                elif len(labelList) != 0:
                    if self.MainGraphicsView.allowScraw and len(labelList) == 1 and not np.any(imgPixmapToNmp(labelList[0].getPixmap())):
                        self.keeplabel(ConflictMode.Coexist)
                    else:
                        self.keep = KeepLabelConflictDialog()
                        self.keep.show()
                        self.keep.signalConflictProcessByMode.connect(lambda conflictmode: self.keeplabel(conflictmode))
                else:
                    self.keeplabel(ConflictMode.Coexist)
        else:
            self.labelKeepboard.clear()
        if self.action_keep_size.isChecked() and self.MainGraphicsView.microImg.width() == lastFileWidth and self.MainGraphicsView.microImg.height() == lastFileHeight:
                self.MainGraphicsView.setScale(lastScale)
                self.MainGraphicsView.setViewCenter(lastCenter)

        # 加载亮度对比度饱和度调整缓存
        self.angle = 0
        # self.brightnessContrastAdjustmentWin.show()

        # 根据右侧类型列表可见范围展示标注
        typeList = list(self.project.getTypes())
        for i in range(self.ui.tableWidget.rowCount()):
            self.MainGraphicsView.setLabelHide(typeList[i], self.project.getShowByType(typeList[i]))

    '''
    顶部工具栏
    '''

    def loadRawImg(self):
        '''
        点击原图按钮后被调用，将图像切换为原图
        '''
        currentFile = self.project.importFiles[self.lastFileIndex]
        rawImgFile = os.path.join(self.project.rawDataDir, currentFile['path'])
        self.MainGraphicsView.temporalLoadRawImage(rawImgFile)

    def setBrushValue(self):
        '''
        设置画刷大小数值
        :return:
        '''
        value = self.ui.horizontalSliderBrushSize.value()
        self.ui.labelBrushSizeValue.setText("{}%".format(value))
        if self.MainGraphicsView.scrawCursor:
            self.MainGraphicsView.scrawCursor.cursorWidth = value
            for item in self.MainGraphicsView.items():
                if isinstance(item, ScrawLabel):
                    item.penWidth = value

    def changeBrushValue(self, enlarge=True):
        '''
        快捷键修改笔刷
        '''
        value = self.ui.horizontalSliderBrushSize.value()
        if enlarge:
            if value >= 100:
                self.ui.horizontalSliderBrushSize.setValue(100)
            else:
                self.ui.horizontalSliderBrushSize.setValue(min(100, value + 5))
        else:
            if value <= 0:
                self.ui.horizontalSliderBrushSize.setValue(0)
            else:
                self.ui.horizontalSliderBrushSize.setValue(max(0, value - 5))
        self.setBrushValue()

    def changeThresholdValue(self, enlarge=True):
        value = self.ui.horizontalSliderThreshold.value()
        if enlarge:
            if value >= 100:
                self.ui.horizontalSliderThreshold.setValue(100)
            else:
                self.ui.horizontalSliderThreshold.setValue(min(100, value + 5))
        else:
            if value <= 0:
                self.ui.horizontalSliderThreshold.setValue(0)
            else:
                self.ui.horizontalSliderThreshold.setValue(max(0, value - 5))


    # def setSensibilityValue(self):
    #     '''
    #     设置画刷大小数值
    #     :return:
    #     '''
    #     value = self.ui.horizontalSliderSensibility.value()
    #     self.ui.labelSensibilityValue.setText("{}%".format(value))

    def updateScissorsArea(self, value):
        # 更新变量值
        self.MainGraphicsView.square_size = value
        # 更新标签显示
        self.ui.ScissorsArea.setText(f"搜索区域:")
        self.MainGraphicsView.viewport().update()

    def updatePointNum(self, value):
        # 更新变量值
        self.MainGraphicsView.ScissorspPointNum = value
        # 更新标签显示
        self.ui.PointNum.setText(f"点间隔:")

    def hideBtnSetting(self):
        '''
        隐藏左侧工具栏点击后对应的设置
        :return:
        '''
        self.ui.widgetSensibility.setVisible(False)
        self.ui.widgetBrushSize.setVisible(False)
        self.ui.widgetZoom.setVisible(False)
        self.ui.widgetToScrawLabel.setVisible(False)
        self.ui.widgetFill.setVisible(False)
        self.ui.widgetToPolygonLabel.setVisible(False)
        self.ui.widgetAIAnalysis.setVisible(False)
        self.ui.widgetAiModel.setVisible(False)
        self.ui.widgetAiMagic.setVisible(False)
        self.ui.widgetScrawBrush.setVisible(False)
        self.ui.widgetPolygon.setVisible(False)
        # 取消预分割禁用
        self.ui.pushButtonSegmentation.setEnabled(True)


    def updateLabelColor(self, temp_classes: list):
        '''
        更新类别设置、更新右侧列表相应设置
        '''
        # # 更新顶边栏选项
        # orig_keys = list(orig_tags.keys())
        # new_keys = list(self.project.getTypes())
        # # 更新显示label
        # for i in range(len(orig_keys)):
        #     t_key = orig_keys[i]
        #     self.MainGraphicsView.changeLabel(t_key, new_keys[i], QColor(self.project.getColorByType(new_keys[i])))

        for orig_class in self.project.classes:
            flag = False
            for _class in temp_classes:
                if _class["id"] == orig_class["id"]:
                    self.MainGraphicsView.changeLabel(orig_class["type"], _class["type"], _class["color"])
                    flag = True
            if not flag:
                self.MainGraphicsView.deleteLabel(orig_class["type"])

        self.project.classes = copy.deepcopy(temp_classes)

        self.updateTopBarLabel()
        self.updateTopBarColor()
        self.setTypeSideBar()
        self.setTargetSideBar()
        self.thresholdSegmentationWin.setCache(None)

    def updateTopBarLabel(self):
        '''
        更新类别下拉框，并默认选中非背景类
        '''
        new_keys = list(self.project.getTypes())
        self.ui.comboBoxTags.clear()
        self.ui.comboBoxTags.addItems(new_keys)
        bkClass = self.project.getTypeById(0)
        # 将类别下拉框默认为非背景类
        find = False
        for i in range(len(new_keys)):
            if new_keys[i] == bkClass:
                find = True
                break

        if find and i == 0:
            if len(new_keys) == 1:
                self.ui.comboBoxTags.setCurrentIndex(0)
            else:
                self.ui.comboBoxTags.setCurrentIndex(1)
        else:
            self.ui.comboBoxTags.setCurrentIndex(0)

    def updateTopBarColor(self):
        '''
        更新类别设置图块的颜色
        '''
        if self.ui.comboBoxTags.currentText() == "":
            return
        color = self.project.getColorByType(self.ui.comboBoxTags.currentText())
        self.ui.labelPartitionColor.setStyleSheet("width: 26px;\n"
                                                  "height: 26px;\n"
                                                  "border-radius: 3px;\n"
                                                  "background: {};".format(color))

        self.MainGraphicsView.current_color = QColor(color)
        self.MainGraphicsView.current_type = self.ui.comboBoxTags.currentText()
        if self.project.getIdByType(self.ui.comboBoxTags.currentText()) == 0:
            self.MainGraphicsView.is_bgcolor = True
        else:
            self.MainGraphicsView.is_bgcolor = False
        self.checkCurrentClass()
        self.switchWidgetThreshold()
        if self.MainGraphicsView.allowScraw:
            self.MainGraphicsView.changeScrawMode(True)

    def updateAiModel(self):
        #切换模型
        # aimodel = self.project.getAiModel(self.ui.comboBoxModel.currentText())
        # 目前只提供一种方法 efficientvitsam 下拉框功能暂时禁用
        aimodel = "efficientvitsam"
        self.MainGraphicsView.ai_model = aimodel
        self.MainGraphicsView.update_model()

    def SwitchClickmodeon(self):
        self.MainGraphicsView.Clickmode = True
        self.MainGraphicsView.Hovermode = False
        self.MainGraphicsView.allowGrabCut = False
        # 关闭画刷
        self.MainGraphicsView.allowAiScraw = False
        self.MainGraphicsView.allowAIMagic = True
        self.MainGraphicsView.erasermode = False
        self.MainGraphicsView.changeScrawMode(False)
        self.MainGraphicsView.setCursor(Qt.CrossCursor)
        self.MainGraphicsView.setDragMode(QGraphicsView.NoDrag)
        self.MainGraphicsView.changeZoomMode(zoomMode.NoZoom)
        # 清空阈值分割结果
        if self.thresholdSegmentationWin.ui.toolButtonFold.isChecked():
            self.thresholdSegmentationWin.reset()
        self.loadPreSegCache(-1)
        self.MainGraphicsView.endHoverTimer()
        #self.MainGraphicsView.clear_EfficientSAM_label()

    def SwitchHovermodeon(self):
        self.MainGraphicsView.Clickmode = False
        self.MainGraphicsView.Hovermode = True
        self.MainGraphicsView.allowGrabCut = False
        # 关闭画刷
        self.MainGraphicsView.allowAiScraw = False
        self.MainGraphicsView.allowAIMagic = True
        self.MainGraphicsView.erasermode = False
        self.MainGraphicsView.changeScrawMode(False)
        self.MainGraphicsView.setCursor(Qt.CrossCursor)
        self.MainGraphicsView.setDragMode(QGraphicsView.NoDrag)
        self.MainGraphicsView.changeZoomMode(zoomMode.NoZoom)
        # 清空阈值分割结果
        if self.thresholdSegmentationWin.ui.toolButtonFold.isChecked():
            self.thresholdSegmentationWin.reset()
        self.loadPreSegCache(-1)
        # 启动悬浮模式
        self.MainGraphicsView.startHoverTimer()
        # self.MainGraphicsView.timer.stop()

    def SwitchRectmodeon(self):
        #allowGrabCut
        self.MainGraphicsView.allowGrabCut = True
        self.MainGraphicsView.Clickmode = False
        self.MainGraphicsView.Hovermode = False
        # 关闭画刷
        self.MainGraphicsView.allowAiScraw = False
        self.MainGraphicsView.allowAIMagic = True
        self.MainGraphicsView.erasermode = False
        self.MainGraphicsView.changeScrawMode(False)
        self.MainGraphicsView.setCursor(Qt.CrossCursor)
        self.MainGraphicsView.setDragMode(QGraphicsView.RubberBandDrag)
        self.MainGraphicsView.changeZoomMode(zoomMode.NoZoom)
        # 清空阈值分割结果
        if self.thresholdSegmentationWin.ui.toolButtonFold.isChecked():
            self.thresholdSegmentationWin.reset()
        self.loadPreSegCache(-1)
        # 关闭悬浮
        self.MainGraphicsView.endHoverTimer()

    def SwitchBrushmodeon(self):
        self.MainGraphicsView.allowGrabCut = False
        self.MainGraphicsView.Clickmode = False
        self.MainGraphicsView.Hovermode = False
        # 关闭悬浮
        self.MainGraphicsView.endHoverTimer()
        # 启动画刷
        self.MainGraphicsView.brushflag = True
        self.MainGraphicsView.erasermode = False
        self.Aiscraw()
        self.birdView.setVisible(False)
        # 清空阈值分割结果
        if self.thresholdSegmentationWin.ui.toolButtonFold.isChecked():
            self.thresholdSegmentationWin.reset()
        self.loadPreSegCache(-1)

    def SwitchErasermodeon(self):
        self.MainGraphicsView.allowGrabCut = False
        self.MainGraphicsView.Clickmode = False
        self.MainGraphicsView.Hovermode = False
        # 关闭悬浮
        self.MainGraphicsView.endHoverTimer()
        # 启动橡皮擦
        self.MainGraphicsView.brushflag = True
        self.MainGraphicsView.erasermode = True
        self.Aiscraw()
        self.birdView.setVisible(False)
        # 清空阈值分割结果
        if self.thresholdSegmentationWin.ui.toolButtonFold.isChecked():
            self.thresholdSegmentationWin.reset()
        self.loadPreSegCache(-1)

    def SwitchScrawBrushmode(self):
        # 启动画刷
        self.MainGraphicsView.brushflag = True
        self.MainGraphicsView.erasermode = False
        self.Aiscraw()
        self.birdView.setVisible(False)

    def SwitchScrawErasemode(self):
        # 启动橡皮擦
        self.MainGraphicsView.brushflag = True
        self.MainGraphicsView.erasermode = True
        self.Aiscraw()
        self.birdView.setVisible(False)

    def updateComboBoxZoomValue(self, scale):
        '''
        更新放大缩小下拉框文字
        '''
        self.ui.comboBoxZoomValue.currentTextChanged.disconnect()
        self.ui.comboBoxZoomValue.setCurrentIndex(int(scale / 25) - 1)
        self.ui.comboBoxZoomValue.currentTextChanged.connect(
            lambda newtext: self.MainGraphicsView.setScale(int(newtext.replace("%", "")) / 100))

    def convertPolygonToSraw(self):
        waitingWin = WaitingWin(False, '正在将多边形标注转换成涂鸦标注，请稍等...')
        waitingWin.show()
        self.MainGraphicsView.convertPolygonToSraw()
        self.ui.tBtnArrow.click()
        waitingWin.close()

    def convertScrawToPolygon(self):
        waitingWin = WaitingWin(False, '正在将涂鸦标注转换成多边形标注，请稍等...')
        waitingWin.show()
        self.MainGraphicsView.convertScrawToPolygon()
        self.ui.tBtnArrow.click()
        waitingWin.close()

    '''
        窗口页面
    '''

    def maximumStateChange(self):
        '''
        窗口最大化与恢复
        :return:
        '''
        # 全屏状态按下最大化按钮，也会退出全屏缩小
        if self.stateMaximized:
            self.showNormal()
            self.stateMaximized = False
        else:
            self.showMaximized()
            self.stateMaximized = True

    # 双击顶部切换最大化
    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:
        pos = event.pos()
        topRect = QRectF(self.ui.frameTitle.rect())
        if pos.x() <= topRect.bottomRight().x() and pos.y() <= topRect.bottomRight().y():
            self.ui.tBtnMax.click()
        return super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, a0: QtGui.QKeyEvent) -> None:
        # TODO 快捷键alt
        self.MainGraphicsView.keyPressEvent(a0)
        # H或ctrl+H 手势拖
        if a0.key() == Qt.Key_H and (a0.modifiers() == Qt.NoModifier):
            for item in self.project.toolButtons:
                if item['name'] == '手势拖动' and item['activate']:
                    self.ui.tBtnHand.click()
                    break
        if (a0.key() == Qt.Key_H) and (a0.modifiers() == Qt.ControlModifier):
            for item in self.project.toolButtons:
                if item['name'] == '手势拖动' and item['activate']:
                    self.ui.tBtnHand.click()
                    break
        # J或ctrl+J 箭头拖动
        if a0.key() == Qt.Key_J and (a0.modifiers() == Qt.NoModifier):
            for item in self.project.toolButtons:
                if item['name'] == '编辑标注' and item['activate']:#A修改（将箭头指向改为编辑标注）
                    self.ui.tBtnArrow.click()
                    break
        if (a0.key() == Qt.Key_J) and (a0.modifiers() == Qt.ControlModifier):
            for item in self.project.toolButtons:
                if item['name'] == '编辑标注' and item['activate']:#A修改（此处修改同上）
                    self.ui.tBtnArrow.click()
                    break

        # R或ctrl+R 矩形标注
        if a0.key() == Qt.Key_R and (a0.modifiers() == Qt.NoModifier):
            for item in self.project.toolButtons:
                if item['name'] == '矩形标注' and item['activate']:
                    self.ui.tBtnRectangleLabel.click()
                    break
        if (a0.key() == Qt.Key_R) and (a0.modifiers() == Qt.ControlModifier):
            for item in self.project.toolButtons:
                if item['name'] == '矩形标注' and item['activate']:
                    self.ui.tBtnRectangleLabel.click()
                    break
        # P或ctrl+P或N或ctrl+N 多边形标注
        if a0.key() == Qt.Key_P and (a0.modifiers() == Qt.NoModifier):
            for item in self.project.toolButtons:
                if item['name'] == '多边形标注' and item['activate']:
                    self.ui.tBtnPolygonLabel.click()
                    break
        if (a0.key() == Qt.Key_P) and (a0.modifiers() == Qt.ControlModifier):
            for item in self.project.toolButtons:
                if item['name'] == '多边形标注' and item['activate']:
                    self.ui.tBtnPolygonLabel.click()
                    break
        if a0.key() == Qt.Key_N and (a0.modifiers() == Qt.NoModifier):
            for item in self.project.toolButtons:
                if item['name'] == '多边形标注' and item['activate']:
                    self.ui.tBtnPolygonLabel.click()
                    break
        if (a0.key() == Qt.Key_N) and (a0.modifiers() == Qt.ControlModifier):
            for item in self.project.toolButtons:
                if item['name'] == '多边形标注' and item['activate']:
                    self.ui.tBtnPolygonLabel.click()
                    break
        # B或ctrl+B 画刷
        if a0.key() == Qt.Key_B and (a0.modifiers() == Qt.NoModifier):
            if self.ui.tBtnAIMagic.isChecked():
                self.ui.tBtnBrushmode.click()
            elif self.ui.tBtnBrush.isChecked():
                    self.ui.tBtnScrawBrushmode.click()
            else:
                for item in self.project.toolButtons:
                    if item['name'] == '画刷' and item['activate']:
                        self.ui.tBtnBrush.click()
                        break
        if (a0.key() == Qt.Key_B) and (a0.modifiers() == Qt.ControlModifier):
            if self.ui.tBtnAIMagic.isChecked():
                self.ui.tBtnBrushmode.click()
            elif self.ui.tBtnBrush.isChecked():
                    self.ui.tBtnScrawBrushmode.click()
            else:
                for item in self.project.toolButtons:
                    if item['name'] == '画刷' and item['activate']:
                        self.ui.tBtnBrush.click()
                        break
        # .或ctrl+. 点标注
        if a0.key() == Qt.Key_Period and (a0.modifiers() == Qt.NoModifier):
            for item in self.project.toolButtons:
                if item['name'] == '点标注' and item['activate']:
                    self.ui.tBtnPointLabel.click()
                    break
        if (a0.key() == Qt.Key_Period) and (a0.modifiers() == Qt.ControlModifier):
            for item in self.project.toolButtons:
                if item['name'] == '点标注' and item['activate']:
                    self.ui.tBtnPointLabel.click()
                    break
        # L或ctrl+L 直线标注
        if a0.key() == Qt.Key_L and (a0.modifiers() == Qt.NoModifier):
            for item in self.project.toolButtons:
                if item['name'] == '直线标注' and item['activate']:
                    self.ui.tBtnLine.click()
                    break
        if (a0.key() == Qt.Key_L) and (a0.modifiers() == Qt.ControlModifier):
            for item in self.project.toolButtons:
                if item['name'] == '直线标注' and item['activate']:
                    self.ui.tBtnLine.click()
                    break
        # E或ctrl+E 涂鸦或魔术棒下的橡皮擦
        if a0.key() == Qt.Key_E and (a0.modifiers() == Qt.NoModifier):
            if self.ui.tBtnAIMagic.isChecked():
                self.ui.tBtnScrawErasermode.click()
            elif self.ui.tBtnBrush.isChecked():
                self.ui.tBtnScrawErasermode.click()
        if a0.key() == Qt.Key_E and (a0.modifiers() == Qt.ControlModifier):
            if self.ui.tBtnAIMagic.isChecked():
                self.ui.tBtnScrawErasermode.click()
            elif self.ui.tBtnBrush.isChecked():
                self.ui.tBtnScrawErasermode.click()
        # I或ctrl+I或ctrl+shift+A 魔术棒
        if a0.key() == Qt.Key_I and (a0.modifiers() == Qt.NoModifier):
            for item in self.project.toolButtons:
                if item['name'] == '魔术棒' and item['activate']:
                    self.ui.tBtnAIMagic.click()
                    break
        if (a0.key() == Qt.Key_I) and (a0.modifiers() == Qt.ControlModifier):
            for item in self.project.toolButtons:
                if item['name'] == '魔术棒' and item['activate']:
                    self.ui.tBtnAIMagic.click()
                    break
        if (a0.key() == Qt.Key_A) and (a0.modifiers() == (Qt.ControlModifier | Qt.ShiftModifier)):
            for item in self.project.toolButtons:
                if item['name'] == '魔术棒' and item['activate']:
                    self.ui.tBtnAIMagic.click()
                    break
        # shift+P 涂鸦转多边形
        if (a0.key() == Qt.Key_P) and (a0.modifiers() == Qt.ShiftModifier):
            self.ui.tBtnToPolygonLabel.click()
        # space 若为已预测则是确认预测；否则涂鸦转多边形
        if a0.key() == Qt.Key_Space and (a0.modifiers() == Qt.NoModifier):
            if self.ui.pBtnThresholdEnsure.isVisible():
                self.ui.pBtnThresholdEnsure.click()
            else:
                self.ui.tBtnToPolygonLabel.click()
        # shift+B 多边形转涂鸦
        if (a0.key() == Qt.Key_B) and (a0.modifiers() == Qt.ShiftModifier):
            self.ui.tBtnPolygonLabel.click()
            self.ui.tBtnToScrawLabel.click()
        # shift+F 涂鸦孔洞填充
        if (a0.key() == Qt.Key_F) and (a0.modifiers() == Qt.ShiftModifier):
            self.ui.tBtnFill.click()
        # ctrl+A 全选
        if (a0.key() == Qt.Key_A) and (a0.modifiers() == Qt.ControlModifier):
            self.ui.tBtnArrow.click()
            time.sleep(0.1)
            labelList = self.MainGraphicsView.getLabelList()
            for label in labelList:
                if label.labelClass != "Feedback" and label.labelClass != "preseg_scraw" and label.labelClass != "RectCut" and label.labelClass != "Scraw":
                    label.setSelected(True)
        # ctrl+del 删除
        if (a0.key() == Qt.Key_Delete) and (a0.modifiers() == Qt.ControlModifier):
            self.actionDeleteLabel.trigger()
        # ctrl+Q 回到主界面
        if (a0.key() == Qt.Key_Q) and (a0.modifiers() == Qt.ControlModifier):
            self.signalBackHome.emit()
        # ctrl+shift+Q 退出本软件
        if (a0.key() == Qt.Key_Q) and (a0.modifiers() == (Qt.ControlModifier | Qt.ShiftModifier)):
            qApp.exit(0)
        # ctrl+shift+W 适应屏幕
        if (a0.key() == Qt.Key_W) and (a0.modifiers() == (Qt.ControlModifier | Qt.ShiftModifier)):
            self.MainGraphicsView.fitScreen()
        # ctrl+W 填充屏幕
        if (a0.key() == Qt.Key_W) and (a0.modifiers() == Qt.ControlModifier):
            self.MainGraphicsView.fullScreen()
        # ctrl+shift+s 统计分析
        if (a0.key() == Qt.Key_S) and (a0.modifiers() == (Qt.ControlModifier | Qt.ShiftModifier)):
            self.showStatisticAnalyseWin()
            self.MainGraphicsView.click_shift_mode = False
            self.MainGraphicsView.updateScrawCursor()
        # ctrl+F 筛选功能
        if (a0.key() == Qt.Key_F) and (a0.modifiers() == Qt.ControlModifier):
            self.showFilterWin()
        # ctrl+O 导入图像
        if (a0.key() == Qt.Key_O) and (a0.modifiers() == Qt.ControlModifier):
            self.importNewImage()
        # ctrl+U 导入标注与图像
        if (a0.key() == Qt.Key_U) and (a0.modifiers() == Qt.ControlModifier):
            self.showSubWinAndHideMain(self.importPictureAndLabelWin)
        # W 上一张
        if a0.key() == Qt.Key_W and (a0.modifiers() == Qt.NoModifier):
            self.switchImg(self.ui.listwidgetFile.currentRow() - 1)
        # S 下一张
        if a0.key() == Qt.Key_S and (a0.modifiers() == Qt.NoModifier):
            self.switchImg(self.ui.listwidgetFile.currentRow() + 1)
        # pageUp 上一页
        if a0.key() == Qt.Key_PageUp and (a0.modifiers() == Qt.NoModifier):
            self.ui.pushButtonPrePage.click()
        # pageDown 下一页
        if a0.key() == Qt.Key_PageDown and (a0.modifiers() == Qt.NoModifier):
            self.ui.pushButtonNextPage.click()
        # E或者ctrl+E 智能标注
        if a0.key() == Qt.Key_E and (a0.modifiers() == Qt.NoModifier):
            if self.MainGraphicsView.allowAIMagic:
                self.ui.tBtnErasermode.click()
        if a0.key() == Qt.Key_E and (a0.modifiers() == Qt.ControlModifier):
            if self.MainGraphicsView.allowAIMagic:
                self.ui.tBtnErasermode.click()
        return super().keyPressEvent(a0)

    def keyReleaseEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() == Qt.Key_Shift:
            self.MainGraphicsView.click_shift_mode = False
            self.MainGraphicsView.updateScrawCursor()
    '''
        右侧类型列表
    '''

    def addLabelNum(self, type, attribute, current = True):
        '''
        description: 增加type类型的数量,标注属性有涂鸦scraw和实例instance
        type: str, 传入标注的类型，如"类型1"
        attribut: str, 可传入“scraw”或“instance”。也可传入label类型，自动转换成“scraw”或“instance”
        inferCompleted: bool, 传入当前图是否是预测图。若为预测图则不统计
        '''
        if current and self.fileList[self.ui.listwidgetFile.currentRow() + self.pageSize * (self.currentPage - 1)]["inferCompleted"]:
            return
        # 处理特殊标注
        if attribute == "Feedback" or attribute == "preseg_scraw" or attribute == "RectCut":
            return
        elif attribute == "Tag":
            for label in self.MainGraphicsView.labelList:
                if label.labelClass == "Tag":
                    return
        # 处理标注映射
        if attribute == "Scraw":
            attribute = "scraw"
        elif attribute == "Rectangle" or attribute == "PolygonCurve" or attribute == "Point" or attribute == "Tag" or attribute == "Line" or attribute == "Circle":
             attribute = "instance"
        # 处理标注数量
        if attribute == "scraw":
            for label in self.MainGraphicsView.labelList:
                if label.labelClass == "Scraw" and label.type == type and label.Die == False:
                    # 该图层当前已经有同类型涂层，不增涂层数量
                    return
        for item in self.project.classes:
            if item["type"] == type:
                item[attribute] += 1
                break

    def subLabelNum(self, type, attribute, current = True):
        '''
        description: 减少type类型的数量
        tip: 标注属性有涂鸦scraw和实例instance
        attribut: 可传入label类型，也可传入“scraw”或“instance”。自动转换成“scraw”或“instance”
        '''
        if current and self.fileList[self.ui.listwidgetFile.currentRow() + self.pageSize * (self.currentPage - 1)]["inferCompleted"]:
            return
        # 处理特殊标注
        if attribute == "Feedback" or attribute == "preseg_scraw" or attribute == "RectCut":
            return
        # 处理标注映射
        if attribute == "Scraw":
            attribute = "scraw"
        elif attribute == "Rectangle" or attribute == "PolygonCurve" or attribute == "Point" or attribute == "Tag" or attribute == "Line" or attribute == "Circle":
            attribute = "instance"
        # 处理标注数量
        for item in self.project.classes:
            if item["type"] == type and item[attribute] > 0:
                item[attribute] -= 1
                break

    def setTypeSideBar(self):
        '''
        填充类型列表
        '''
        self.ui.checkBoxSelectAll.setChecked(True)
        if len(self.fileList) > 0 and self.ui.listwidgetFile.currentRow() + self.pageSize * (self.currentPage-1) > -1:
            file = self.fileList[self.ui.listwidgetFile.currentRow() + self.pageSize * (self.currentPage-1)]
            imagePath = file['path']
            self.save(imagePath)

        self.ui.tableWidget.clear()
        typeList = list(self.project.getTypes())
        typenum = len(typeList)
        self.ui.tableWidget.setRowCount(typenum)

        for i in range(typenum):
            self.project.setShowByType(typeList[i], True)
            self.MainGraphicsView.setLabelHide(typeList[i], self.project.getShowByType(typeList[i]))
            self.ui.tableWidget.setCellWidget(i, 0,
                                              self.generateShowHideIcon(self.project.getShowByType(typeList[i])))
            # self.ui.tableWidget.setCellWidget(i, 0, QCheckBox())
            self.ui.tableWidget.setCellWidget(i, 1,
                                              self.generateTypeColor(typeList[i]))
            self.ui.tableWidget.setCellWidget(i, 2,
                                              self.generateTypeItem(typeList[i]))

            t_item1 = QTableWidgetItem(str(self.project.getInstanceByType(typeList[i])))
            t_item1.setTextAlignment(Qt.AlignCenter)
            t_item1.setFlags(t_item1.flags() & ~Qt.ItemIsEditable)
            self.ui.tableWidget.setItem(i, 3, t_item1)

            t_item2 = QTableWidgetItem(str(self.project.getScrawByType(typeList[i])))
            t_item2.setTextAlignment(Qt.AlignCenter)
            t_item2.setFlags(t_item2.flags() & ~Qt.ItemIsEditable)
            self.ui.tableWidget.setItem(i, 4, t_item2)

    # 双击类型列表中某一行，当前类型更换
    def changeType(self, row):
        self.ui.comboBoxTags.setCurrentIndex(row)
        color = self.project.getColorByType(self.ui.comboBoxTags.currentText())
        self.ui.labelPartitionColor.setStyleSheet("width: 26px;\n"
                                                    "height: 26px;\n"
                                                    "border-radius: 3px;\n"
                                                    "background: {};".format(color))

    def handleCellClick(self):
        self.timer.start(250)

    def processSingleClick(self):
        self.selected_labels.clear()
        self.selected_indexes.clear()
        self.ui.tBtnArrow.click()
        self.selected_indexes = self.ui.tableWidgetTargetList.selectedIndexes()
        selected_rows = set(index.row() for index in self.selected_indexes)
        for row in selected_rows:
            label = self.MainGraphicsView.getLabelList()[row]
            self.selected_labels.append(label)
        self.MainGraphicsView.selectMoreItem(self.selected_labels)

    def handleCellDoubleClick(self):
        self.timer.stop()

        selmodel = self.ui.tableWidgetTargetList.selectionModel()
        for index in self.selected_indexes:
            selmodel.select(index, QItemSelectionModel.Select)

        # 显示标注转换界面
        if self.selected_labels:
            self.showChangeType(self.selected_labels)
        # 重置
        self.selected_labels = []

    def showChangeType(self, labels):
        self.ui.tBtnArrow.click()
        self.MainGraphicsView.selectMoreItem(labels)
        if self.ChangeTypeDialog:
            self.ChangeTypeDialog.close()
        self.comboBoxTags_text = self.ui.comboBoxTags.currentText()

        self.ChangeTypeDialog = ChangeType(labels, self.comboBoxTags_text, self, self.project)
        self.ChangeTypeDialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.ChangeTypeDialog.labelNumChanged.connect(self.setTypeSideBar)
        self.ChangeTypeDialog.labelNumChanged.connect(self.setTargetSideBar)
        self.ChangeTypeDialog.labelNumChanged.connect(self.setCurLabelStatus)
        self.ChangeTypeDialog.singleSubLabelNum.connect(self.subLabelNum)
        self.ChangeTypeDialog.singleAddLabelNum.connect(self.addLabelNum)
        self.ChangeTypeDialog.show()

    def generateTypeColor(self, type):
        t_widget = QWidget()
        t_layout = QHBoxLayout()
        t_layout.setContentsMargins(0, 0, 0, 0)
        t_label = QLabel()
        t_pixmap = QPixmap(20, 20)
        t_pixmap.fill(QColor(self.project.getColorByType(type)))
        t_label.setFixedSize(20, 20)
        t_label.setPixmap(t_pixmap)
        t_layout.addWidget(t_label)

        t_widget.setLayout(t_layout)
        t_widget.setStyleSheet("background:transparent;")
        return t_widget

    def generateTypeItem(self, type):
        t_widget = QWidget()
        t_layout = QHBoxLayout()
        t_layout.setContentsMargins(0, 0, 0, 0)
        t_label = QLabel(type)
        t_label.setAlignment(Qt.AlignCenter)
        t_layout.addWidget(t_label)

        t_widget.setLayout(t_layout)
        t_widget.setStyleSheet("background:transparent;")
        return t_widget

    def generateShowHideIcon(self, show):
        '''
        生成类型列表可见按钮
        '''
        t_widget = QWidget()
        t_layout = QHBoxLayout()
        # if show:
        #     show_icon = QPixmap(os.path.join(os.getcwd(), "wisdom_store/ui/main/resources/show.png"))
        # else:
        #     show_icon = QPixmap(os.path.join(os.getcwd(), "wisdom_store/ui/main/resources/hide.png"))

        # show_icon = show_icon.scaled(20, 20)

        q_checkbox = QCheckBox()
        q_checkbox.setChecked(show)
        # q_checkbox.setEnabled(False)
        q_checkbox.stateChanged.connect(lambda: self.getClickShowHide(q_checkbox))

        # q_checkbox.setPixmap(show_icon)
        # q_checkbox.resize(20, 20)
        t_layout.addWidget(q_checkbox)
        t_layout.setAlignment(q_checkbox, Qt.AlignCenter)
        t_layout.setContentsMargins(0, 0, 0, 0)
        t_widget.setLayout(t_layout)
        t_widget.setStyleSheet("background:transparent;")
        return t_widget

    def getClickShowHide(self, checkbox):
        '''
        点击可见按钮
        '''
        widget = checkbox.parentWidget()
        parentWidget = checkbox.parentWidget().parentWidget().parentWidget()
        if parentWidget == self.ui.tableWidget:
            if self.ui.tabWidget.currentIndex() != 0:
                return
            modelIndex = self.ui.tableWidget.indexAt(QPoint(widget.frameGeometry().x(), widget.frameGeometry().y()))
            self.changeShowHide(modelIndex.row(), modelIndex.column())

        elif parentWidget is self.ui.tableWidgetTargetList:
            modelIndex = self.ui.tableWidgetTargetList.indexAt(
                QPoint(widget.frameGeometry().x(), widget.frameGeometry().y()))
            self.changeShowHideTarget(modelIndex.row(), modelIndex.column())

    def changeShowHide(self, row, col):
        '''
        转换标注可见状态
        '''
        if col != 0:
            return
        typeList = list(self.project.getTypes())
        self.project.setShowByType(typeList[row], not self.project.getShowByType(typeList[row]))
        self.ui.tableWidget.setCellWidget(row, 0,
                                          self.generateShowHideIcon(self.project.getShowByType(typeList[row])))

        self.MainGraphicsView.setLabelHide(typeList[row], self.project.getShowByType(typeList[row]))
        if False in [_class["isshow"] for _class in self.project.classes]:
            self.ui.checkBoxSelectAll.setChecked(False)
        elif False not in [_class["isshow"] for _class in self.project.classes]:
            self.ui.checkBoxSelectAll.setChecked(True)

    def changeShowHideTarget(self, row, col):
        '''
        转换标注可见状态
        '''
        if col != 0:
            return
        self.targetListShow[row][1] = not self.targetListShow[row][1]
        self.ui.tableWidgetTargetList.setCellWidget(row, 0,
                                          self.generateShowHideIcon(self.targetListShow[row][1]))

        self.MainGraphicsView.setLabelHideTarget(self.targetListShow[row][0], self.targetListShow[row][1])
        if False in [item[1] for item in self.targetListShow]:
            self.ui.checkBoxSelectAll_2.setChecked(False)
        else:
            self.ui.checkBoxSelectAll_2.setChecked(True)

    def changeAllShowHide(self):
        '''
        转换标注可见状态
        '''
        t_checkBox = self.ui.checkBoxSelectAll
        t_state = t_checkBox.checkState()
        # t_checkBox.setChecked(not t_state)
        for i in range(self.ui.tableWidget.rowCount()):
            typeList = list(self.project.getTypes())
            self.project.setShowByType(typeList[i], t_state)
            self.ui.tableWidget.setCellWidget(i, 0,
                                              self.generateShowHideIcon(self.project.getShowByType(typeList[i])))

            self.MainGraphicsView.setLabelHide(typeList[i], self.project.getShowByType(typeList[i]))

    def changeAllShowHideTarget(self):
        '''
        转换标注可见状态
        '''
        t_checkBox = self.ui.checkBoxSelectAll_2
        t_state = t_checkBox.checkState()
        # t_checkBox.setChecked(not t_state)
        for i in range(self.ui.tableWidgetTargetList.rowCount()):
            self.targetListShow[i][1] = t_state
            self.ui.tableWidgetTargetList.setCellWidget(i, 0,
                                          self.generateShowHideIcon(self.targetListShow[i][1]))
            self.MainGraphicsView.setLabelHideTarget(self.targetListShow[i][0], self.targetListShow[i][1])

    '''
        右侧目标列表
    '''

    def setTargetSideBar(self):
        '''
        填充目标列表
        '''
        self.ui.checkBoxSelectAll_2.setChecked(True)
        self.ui.tableWidgetTargetList.clear()
        self.targetListShow.clear()
        labelList = self.MainGraphicsView.getValidLabelList()
        count = len(labelList)
        self.ui.tableWidgetTargetList.setRowCount(count)
        real = 0
        for i in range(count):
            self.project.setShowByType(labelList[i].type, True)
            self.targetListShow.append([labelList[i].id, True])
            # self.MainGraphicsView.setLabelHideTarget(self.targetListShow[i][0], self.targetListShow[i][1])
            self.MainGraphicsView.setLabelHideTarget(labelList[i].id , True)
            self.ui.tableWidgetTargetList.setCellWidget(i, 0,
                                                        self.generateShowHideIcon(
                                                            self.project.getShowByType(labelList[i].type)))
            self.ui.tableWidgetTargetList.setCellWidget(real, 1, self.generateTypeColor(labelList[i].type))
            self.ui.tableWidgetTargetList.setCellWidget(real, 2, self.generateTypeItem(labelList[i].type))

            if str(labelList[i].labelClass) == 'preseg_scraw' or str(labelList[i].labelClass) == 'RectCut':
                continue

            t_item = QTableWidgetItem(labelClassDict[str(labelList[i].labelClass)])
            t_item.setTextAlignment(Qt.AlignCenter)
            t_item.setFlags(t_item.flags() & ~Qt.ItemIsEditable)
            self.ui.tableWidgetTargetList.setItem(real, 3, t_item)
            if not math.isnan(labelList[i].confidence):
                confstr = "{:.2f}".format(labelList[i].confidence)
            else:
                confstr = '\\'
            t_item = QTableWidgetItem(confstr)
            t_item.setTextAlignment(Qt.AlignCenter)
            t_item.setFlags(t_item.flags() & ~Qt.ItemIsEditable)
            self.ui.tableWidgetTargetList.setItem(real, 4, t_item)
            # t_item = QTableWidgetItem(labelList[i].operator)
            # t_item.setFlags(t_item.flags() & ~Qt.ItemIsEditable)
            # self.ui.tableWidgetTargetList.setItem(real, 2, t_item)
            real += 1

    def setViewAtLabel(self, row, col):
        '''
        点击列表后主视图对准点击的你那个标注
        '''
        labelList = self.MainGraphicsView.getLabelList()
        labelindex = None
        for i in range(len(labelList)):
            if labelList[i].Die == True:
                continue
            else:
                if row == 0:
                    labelindex = i
                    break
                row = row - 1
        if labelindex is not None:
            newPoint = labelList[labelindex].shape().boundingRect().center() / labelList[labelindex].scale
            self.MainGraphicsView.setViewCenter(newPoint)
            labelList[labelindex].focused = True

    '''
        右侧折叠栏
    '''

    # def transStackedWidgetLabel(self, toBrief, index=-1):
    #     if toBrief:
    #         self.ui.pageLabelBrief.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
    #         self.ui.pageLabelDetailed.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
    #         nextIndex = 0
    #     else:
    #         self.ui.pageLabelBrief.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
    #         self.ui.pageLabelDetailed.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
    #         nextIndex = 1
    #     self.ui.stackedWidgetLabel.adjustSize()
    #     self.ui.stackedWidgetLabel.setCurrentIndex(nextIndex)
    #     targetBotton = [self.ui.toolButtonTypeList, self.ui.toolButtonTargetList, self.ui.toolButtonLog]
    #     for botton in targetBotton:
    #         botton.setChecked(False)
    #     if index != -1:
    #         self.ui.tabWidget.setCurrentIndex(index)
    #         targetBotton[index].setChecked(True)

    def transWidgetManipulation(self, toBrief):
        if toBrief:
            # self.ui.widgetFoldingBar.setVisible(True)
            self.ui.widgetManipulation.setVisible(False)
            self.ManipulationState = False
            self.actionManipulation.setChecked(False)
        else:
            # self.ui.widgetFoldingBar.setVisible(False)
            self.ui.widgetManipulation.setVisible(True)
            self.ManipulationState = True
            self.actionManipulation.setChecked(True)

    def transWidgetSegmentation(self):
        self.ui.pushButtonSegmentation.setChecked(True)
        self.ui.widgetEnhancement.setVisible(False)
        self.ui.widgetSegmentation.setVisible(True)
        #1修改
        self.ui.widgetProcessing.setVisible(False)
        #self.ui.pushButtonProcessing.setChecked(False)

        if hasattr(self,'thresholdSegmentationWin') and self.thresholdSegmentationWin.ui.toolButtonFold.isChecked():
            self.thresholdSegmentationWin.show()
        # self.thresholdSegmentationWin.show()
        self.ui.labelMethod.setText('图像预分割方法：')

    def transWidgetEnhancement(self):
        self.ui.pushButtonEnhancement.setChecked(True)
        self.ui.widgetEnhancement.setVisible(True)
        self.ui.widgetSegmentation.setVisible(False)
        #1修改
        #self.ui.pushButtonProcessing.setChecked(False)
        self.ui.widgetProcessing.setVisible(False)

        if hasattr(self,'thresholdSegmentationWin') and self.thresholdSegmentationWin.ui.toolButtonFold.isChecked():
            self.thresholdSegmentationWin.hide()
        self.ui.labelMethod.setText('原图增强方法：')

    #1修改
    def transWidgetProcessing(self):
        self.ui.pushButtonProcessing.setChecked(True)
        self.ui.widgetProcessing.setVisible(True)
        self.ui.widgetEnhancement.setVisible(False)
        self.ui.widgetSegmentation.setVisible(False)

        if hasattr(self, 'thresholdSegmentationWin') and self.thresholdSegmentationWin.ui.toolButtonFold.isChecked():
            self.thresholdSegmentationWin.hide()  # Or specific preview reset

        self.ui.labelMethod.setText('标注后处理方法：')
        # if self.labelShowWin.ui.toolButtonFold.isChecked():
        #     self.labelShowWin.show()
        # if self.morphologyWin.ui.toolButtonFold.isChecked():
        #     self.morphologyWin.show()
        #     self.check_morphology_conditions_and_show()



    def showResetWin(self):
        self.cancelWin = DeleteTypeWin()
        if self.ui.pushButtonEnhancement.isChecked():
            self.cancelWin.show('enhance',-1,-1)
            self.cancelWin.ui.labelTitle.setText("原图增强")
            self.cancelWin.ui.pBtnOK.setText("重置")
            self.cancelWin.ui.labelSelections.setText("请问是否要重置当前图像的增强效果？")
            self.cancelWin.signalCloseDelete.connect(self.resetEnhancedImg)
        elif self.ui.pushButtonSegmentation.isChecked():
            self.cancelWin.show('segmentation',-1,-1)
            self.cancelWin.ui.labelTitle.setText("图像预分割")
            self.cancelWin.ui.pBtnOK.setText("重置")
            self.cancelWin.ui.labelSelections.setText("请问是否要重置当前图像的涂鸦/预分割标注？")
            self.cancelWin.signalCloseDelete.connect(self.resetPreSegLabel) #1修改（下一句elif）
        elif self.ui.pushButtonProcessing.isChecked():
            self.cancelWin.show('processing', -1, -1)
            self.cancelWin.ui.labelTitle.setText("标注后处理")
            self.cancelWin.ui.pBtnOK.setText("重置")
            self.cancelWin.ui.labelSelections.setText(
                "请问是否要重置当前图像的标注后处理效果？")
            self.cancelWin.signalCloseDelete.connect(self.resetProcessing)

    #1修改，重置标注后处理（之后再写完整）
    def resetProcessing(self):
        if hasattr(self.project, 'labelAlpha') and hasattr(self.project, 'labelAlphaSelect'):
            self.labelShowWin.AlphaChanged.emit(self.project.labelAlpha)
            self.labelShowWin.AlphaSelectChanged.emit(self.project.labelAlphaSelect)
            self.labelShowWin.mainWin.sliderTransparency.setValue(
                self.labelShowWin.transparency(self.project.labelAlpha))
            self.labelShowWin.mainWin.sliderSelectedTransparency.setValue(
                self.labelShowWin.transparency(self.project.labelAlphaSelect))
        else:
            self.labelShowWin.reset()

        # 重置形态学变换
        self.MainGraphicsView.resetMorphologyPreview()
        self.morphologyWin.reset()
        self.check_morphology_conditions_and_show()

    def resetPreSegLabel(self):
        self.thresholdSegmentationWin.reset()
        for label in self.MainGraphicsView.getLabelList():
            if type(label) == ScrawLabel and label.Die == False and label.confidence == 1:
                self.subLabelNum(label.type, label.labelClass)
                label.Die = True
                label.setVisible(False)
        self.changeFile(self.ui.listwidgetFile.currentRow())

    def resetEnhancedImg(self):
        if self.brightnessContrastAdjustmentWin.ui.toolButtonFold.isChecked():
            self.brightnessContrastAdjustmentWin.ui.toolButtonFold.setChecked(False)
            self.brightnessContrastAdjustmentWin.resetWithoutSignal()
            self.brightnessContrastAdjustmentWin.ui.widgetMain.setVisible(False)
        if self.histogramAdjustmentWin.ui.toolButtonFold.isChecked():
            self.histogramAdjustmentWin.ui.toolButtonFold.setChecked(False)
            self.histogramAdjustmentWin.trans()
        row = self.ui.listwidgetFile.currentRow() + self.pageSize * (self.currentPage-1)
        modified_img = os.path.join(self.project.modifiedImgDir, os.path.basename(self.fileList[row]['path']))
        self.fileList[row]['path'] = os.path.join(self.project.rawDataDir, os.path.basename(self.fileList[row]['path']))
        if os.path.isfile(modified_img):
            os.remove(modified_img)
        # self.MainGraphicsView.openNewImage(os.path.join(self.project.rawDataDir, os.path.basename(self.fileList[row]['path'])))
        tImg = QImage(os.path.join(self.project.rawDataDir, os.path.basename(self.fileList[row]['path'])))
        self.MainGraphicsView.imgArray = np.array(ImageQt.fromqpixmap(tImg))
        self.MainGraphicsView.origImg = QPixmap.fromImage(tImg)
        self.MainGraphicsView.microImg = QPixmap.fromImage(tImg)
        self.MainGraphicsView.myScene.removeItem(self.MainGraphicsView.microImgItem)
        self.MainGraphicsView.microImgItem = QGraphicsPixmapItem(self.MainGraphicsView.microImg)
        self.MainGraphicsView.microImgItem.setScale(self.MainGraphicsView._scale)
        self.MainGraphicsView.microImgItem.setZValue(-2000)
        self.MainGraphicsView.myScene.addItem(self.MainGraphicsView.microImgItem)
        self.MainGraphicsView.fitScreen()
        self.MainGraphicsView.update()
        self.updateListWidgetFile(row)

    def transWidgetStatistics(self, toBrief, index=-1):
        if toBrief:
            # self.ui.widgetFoldingBar.setVisible(True)
            self.ui.widgetStatistics.setVisible(False)
            self.StatisticsState = False
            self.actionStatistic.setChecked(False)
        else:
            # self.ui.widgetFoldingBar.setVisible(False)
            self.ui.widgetStatistics.setVisible(True)
            self.StatisticsState = True
            self.actionStatistic.setChecked(True)

        targetBotton = [self.ui.toolButtonTypeList, self.ui.toolButtonTargetList, self.ui.toolButtonLog]
        if index != -1:
            self.ui.tabWidget.setCurrentIndex(index)
            targetBotton[index].setChecked(True)

        if index == 0:
            self.setTypeSideBar()
        elif index == 1:
            self.setTargetSideBar()

    '''
        底部
    '''

    def updatePixelString(self, s):
        '''
        右下角坐标值与像素值
        '''
        if s is not None:
            self.ui.labelPixelInformation.setText(s)

    '''
        纵向工具栏
    '''

    def updateToolBtnSlot(self):
        print("updateToolBtnSlot")
        if self.ui.tBtnHand.isChecked():
            self.slotTBtnHand()
        elif self.ui.tBtnArrow.isChecked():
            self.slotTBtnArrow()
        elif self.ui.tBtnBrush.isChecked():
            self.slotTBtnBrush()
        elif self.ui.tBtnZoom.isChecked():
            self.slotTBtnZoom()
        elif self.ui.tBtnRectangleLabel.isChecked():
            self.slotTBtnRect()
        elif self.ui.tBtnPolygonLabel.isChecked():
            self.slotTBtnPoly()
        elif self.ui.tBtnLine.isChecked():
            self.slotTBtnLine()
        elif self.ui.tBtnPointLabel.isChecked():
            self.slotTBtnPoint()
        elif self.ui.tBtnTag.isChecked():
            self.slotTBtnTag()
        elif self.ui.tBtnCircle.isChecked():
            self.slotTBtnCircle()
        elif self.ui.tBtnAIMagic.isChecked():
            self.slotTBtnAIMagic()
    def checkCurrentClass(self):
        '''
        设置背景类别下部分工具按钮不可用
        '''
        bgClassName = self.project.getTypeById(0)
        currentClassName = self.ui.comboBoxTags.currentText()
        if bgClassName == currentClassName:
            tools = self.project.toolButtons
            for tool in tools:
                toolObj = self.getToolObjByName(tool['name'])
                if toolObj is None:
                    continue
                if tool['name'] not in ['手势拖动', '箭头指向', '放大镜', '画刷', '统计分析']:
                    toolObj.setChecked(False)
                    toolObj.setEnabled(False)
                else:
                    toolObj.setChecked(False)
                    toolObj.setEnabled(True)
            toolObj = self.getToolObjByName('手势拖动')
            toolObj.setChecked(True)
            self.slotTBtnHand()
        else:
            tools = self.project.toolButtons
            for tool in tools:
                toolObj = self.getToolObjByName(tool['name'])
                if toolObj is None:
                    continue
                toolObj.setEnabled(True)

    from PyQt5 import QtGui  # 导入 QtGui 以使用 QIcon

    def slotChangeScrollAreaPreviewHide(self):
        '''
        左侧预览窗格显示与隐藏
        :return:
        '''
        # 切换预览窗格的显示状态
        self.state_scrollAreaPreview_hide = not self.state_scrollAreaPreview_hide

        # 根据状态更新 UI
        if self.state_scrollAreaPreview_hide:
            # 隐藏预览窗格
            self.ui.widgetFileListPanel.setVisible(False)
            self.actionFileList.setChecked(False)
            self.ui.tBtnCollapse.setToolTip(QtCore.QCoreApplication.translate("Main", "展开"))
            # 设置按钮图标为“展开”图标
            self.ui.tBtnCollapse.setIcon(QtGui.QIcon(r"D:\pycharm_python_project\Annotation-master\展开列表新.png"))
        else:
            # 显示预览窗格
            self.ui.widgetFileListPanel.setVisible(True)
            self.actionFileList.setChecked(True)
            self.ui.tBtnCollapse.setToolTip(QtCore.QCoreApplication.translate("Main", "折叠"))
            # 设置按钮图标为“折叠”图标
            self.ui.tBtnCollapse.setIcon(QtGui.QIcon(r"D:\pycharm_python_project\Annotation-master\收起列表新.png"))

    def slotTBtnHand(self):
        '''
        手型按钮槽函数
        :return:
        '''
        self.hideBtnSetting()
        # 显示上方工具栏对应设置
        self.ui.widgetSensibility.setVisible(True)
        self.handTool()
        self.birdView.setVisible(True)

    def slotTBtnArrow(self):
        '''
        箭头按钮槽函数
        :return:
        '''
        self.hideBtnSetting()
        # 显示上方工具栏对应设置
        self.ui.widgetSensibility.setVisible(True)
        self.arrowTool()
        self.birdView.setVisible(False)




    def slotTBtnBrush(self):
        '''
        画刷按钮点击槽函数
        :return:
        '''
        for label in self.MainGraphicsView.labelList:
            if label.labelClass == "Feedback" or label.labelClass == "RectCut":
                continue
            if label.Die != True:
                if label.confidence != 1:
                    alertWarning(self, "警告", "当前图像存在已预测标注结果，无法进行人工涂鸦标注，请先确认或删除该预测标注", "Error Occurred!")
                    self.ui.tBtnHand.setChecked(True)
                    self.slotTBtnHand()
                    return
                if label.labelClass == "preseg_scraw":
                    alertWarning(self, "警告", "当前图像存在预分割标注结果，无法进行人工涂鸦标注，请先确认或删除该预分割标注", "Error Occurred!")
                    self.ui.tBtnHand.setChecked(True)
                    self.slotTBtnHand()
                    return
        self.hideBtnSetting()
        # 显示上方工具栏对应设置
        self.ui.widgetBrushSize.setVisible(True)
        self.ui.widgetFill.setVisible(True)
        self.ui.widgetToPolygonLabel.setVisible(True)
        self.ui.widgetScrawBrush.setVisible(True)
        self.scrawLabel()
        self.birdView.setVisible(False)
        # self.loadPreSegCache(-1)

    #1修改，定义函数只对人工标注的mask做形态学变换
    def check_morphology_conditions_and_show(self):
        if not hasattr(self, 'morphologyWin') or self.lastFileIndex == -1:
            if hasattr(self, 'morphologyWin'):
                pass
                # self.morphologyWin.win.setEnabled(False)
                # self.morphologyWin.mainWin.comboBoxOperationType.setEnabled(False)
                # self.morphologyWin.mainWin.sliderParameterName.setEnabled(False)
                # self.morphologyWin.mainWin.pBtnApplyMorphological.setEnabled(False)
            return

        current_target_type = self.morphologyWin.mainWin.comboBoxTargetType.currentText()
        if not current_target_type and self.morphologyWin.mainWin.comboBoxTargetType.count() > 0:
            current_target_type = self.morphologyWin.mainWin.comboBoxTargetType.itemText(0)

        active_manual_scraw_for_target = False
        has_predicted_scraw_for_target = False  # 是否有针对当前目标类型的预测涂鸦
        has_any_manual_scraw = False

        for label in self.MainGraphicsView.getLabelList():
            if isinstance(label, ScrawLabel) and not label.Die:
                if label.confidence == 1.0:  # 人工标注
                    has_any_manual_scraw = True
                    if label.type == current_target_type:
                        active_manual_scraw_for_target = True
                elif label.type == current_target_type:  # 预测标注
                    has_predicted_scraw_for_target = True

        enable_morphology = active_manual_scraw_for_target

        # self.morphologyWin.win.setEnabled(enable_morphology)
        # self.morphologyWin.mainWin.comboBoxOperationType.setEnabled(enable_morphology)
        # self.morphologyWin.mainWin.sliderParameterName.setEnabled(enable_morphology)
        # self.morphologyWin.mainWin.pBtnApplyMorphological.setEnabled(enable_morphology)

        if not enable_morphology:
            self.MainGraphicsView.resetMorphologyPreview()  # 如果不满足条件，重置预览
            if not current_target_type and self.morphologyWin.mainWin.comboBoxTargetType.count() == 0:
                alertInfo(self, "提示", "请先在“编辑-设定目标类型”中定义类别。")
            elif not active_manual_scraw_for_target and current_target_type:
                if has_predicted_scraw_for_target:
                    alertInfo(self, "提示",
                              f"目标类型“{current_target_type}”存在预测涂鸦，请先将其转换为人工标注，再进行形态学处理。")
                else:
                    alertInfo(self, "提示",
                              f"当前图像没有“{current_target_type}”类型的人工画刷标注，请标注后再进行后处理。")
            elif not has_any_manual_scraw: # 只有在完全没有任何手动涂鸦时才提示这个
                alertInfo(self, "提示", "当前图像没有人工画刷标注，请标注后再进行后处理。")

        else:  # 条件满足，可以触发一次更新
            self.MainGraphicsView.handleMorphologyTargetTypeChanged(current_target_type)  # 确保预览基于当前类型
            self.MainGraphicsView.handleMorphologyOperationChanged(
                self.morphologyWin.mainWin.comboBoxOperationType.currentText())
            self.MainGraphicsView.handleMorphologyParameterChanged(
                self.morphologyWin.mainWin.sliderParameterName.value())

    def _connect_morphology_signals(self):
        """连接形态学操作信号"""
        self.morphologyWin.TargetTypeChanged.connect(self.MainGraphicsView.changeTargetType)
        self.morphologyWin.OperationTypeChanged.connect(self.MainGraphicsView.changeOperationType)
        self.morphologyWin.ParameterChanged.connect(self.MainGraphicsView.changeParameter)
        self.morphologyWin.MorphologyReset.connect(self.MainGraphicsView.resetMorphology)

    def _disconnect_morphology_signals(self):
        """断开形态学操作信号"""
        try:
            self.morphologyWin.TargetTypeChanged.disconnect(self.MainGraphicsView.changeTargetType)
            self.morphologyWin.OperationTypeChanged.disconnect(self.MainGraphicsView.changeOperationType)
            self.morphologyWin.ParameterChanged.disconnect(self.MainGraphicsView.changeParameter)
            self.morphologyWin.MorphologyReset.disconnect(self.MainGraphicsView.resetMorphology)
        except TypeError:
            # 处理信号未连接的情况
            pass



    def slotTBtnZoom(self):
        '''
        缩放按钮点击槽函数
        :return:
        '''
        self.hideBtnSetting()
        # 显示上方工具栏对应设置
        self.ui.widgetZoom.setVisible(True)
        # self.magnifyTool()
        self.zoomTool()
        self.birdView.setVisible(True)
        self.slotTBtnEnlarge()

    def slotTBtnRect(self):
        self.hideBtnSetting()
        # self.ui.widgetToScrawLabel.setVisible(True)
        self.rectangleLabel()
        self.birdView.setVisible(False)

    def slotTBtnPoly(self):
        self.hideBtnSetting()
        self.ui.widgetToScrawLabel.setVisible(True)
        self.ui.widgetPolygon.setVisible(True)
        self.ui.PointNum.setVisible(False)
        self.ui.PointNumSlider.setVisible(False)
        self.ui.ScissorsArea.setVisible(False)
        self.ui.ScissorsAreaSlider.setVisible(False)
        self.ui.tBtnOriginPolygonLabel.setChecked(True)
        self.ui.tBtnIntelligentScissors.setChecked(False)
        self.polygonLabel()
        self.birdView.setVisible(False)

    def slotTBtnLine(self):
        self.hideBtnSetting()
        self.lineLabel()
        self.birdView.setVisible(False)

    def slotTBtnPoint(self):
        self.hideBtnSetting()
        self.pointLabel()
        self.birdView.setVisible(False)

    def slotTBtnTag(self):
        self.hideBtnSetting()
        self.tagLabel()
        self.birdView.setVisible(False)

    def slotTBtnCircle(self):
        self.hideBtnSetting()
        self.ui.widgetToScrawLabel.setVisible(True)
        self.circleLabel()
        self.birdView.setVisible(False)

    def slotTBtnEnlarge(self):
        self.MainGraphicsView.changeZoomMode(zoomMode.ZoomIn)
        self.ui.tBtnEnlarge.setStyleSheet(r'QToolButton{image: url(:/resources/放大选中.png)}')
        self.ui.tBtnNarrow.setStyleSheet(r'QToolButton{image: url(:/resources/缩小按钮.png)}')

    def slotTBtnNarrow(self):
        self.MainGraphicsView.changeZoomMode(zoomMode.ZoomOut)
        self.ui.tBtnEnlarge.setStyleSheet(r'QToolButton{image: url(:/resources/放大按钮.png)}')
        self.ui.tBtnNarrow.setStyleSheet(r'QToolButton{image: url(:/resources/缩小选中.png)}')

    def slotTBtnCrop(self):
        if self.labelCheck(mode='crop'):
            self.hideBtnSetting()
            self.rectangleCut()
            self.birdView.setVisible(False)


    def slotTBtnAIMagic(self):
        '''
        智能标注按钮触发
        '''
        # 清空阈值分割结果
        if self.thresholdSegmentationWin.ui.toolButtonFold.isChecked():
            self.thresholdSegmentationWin.reset()
        self.loadPreSegCache(-1)
        # 判断预测结果
        for label in self.MainGraphicsView.labelList:
            if label.labelClass == "Feedback" or label.labelClass == "RectCut":
                continue
            if label.Die != True:
                if label.confidence != 1:
                    alertWarning(self, "警告", "当前图像存在已预测标注结果，无法进行人工涂鸦标注，请先确认或删除该预测标注", "Error Occurred!")
                    self.ui.tBtnHand.setChecked(True)
                    self.slotTBtnHand()
                    return
                # if label.labelClass == "preseg_scraw":
                #     alertWarning(self, "警告", "当前图像存在预分割标注结果，无法进行人工涂鸦标注，请先确认或删除该预分割标注", "Error Occurred!")
                #     self.ui.tBtnHand.setChecked(True)
                #     self.slotTBtnHand()
                #     return
        # 按钮显示设定
        self.hideBtnSetting()
        self.ui.widgetToPolygonLabel.setVisible(True)
        self.ui.widgetAiMagic.setVisible(True)
        self.ui.widgetBrushSize.setVisible(True)
        self.ui.widgetAiModel.setVisible(False)
        self.AIMagic()
        self.birdView.setVisible(False)
        # 禁止启动预分割
        if self.ui.pushButtonSegmentation.isChecked():
            self.transWidgetEnhancement()
        self.ui.pushButtonSegmentation.setEnabled(False)

    def slotTBtnZoom(self, isEnlarge=True):
        '''
        缩放按钮点击槽函数
        :return:
        '''
        self.ui.tBtnZoom.setChecked(True)
        self.hideBtnSetting()
        # 显示上方工具栏对应设置
        self.ui.widgetZoom.setVisible(True)
        # self.magnifyTool()
        self.zoomTool()
        self.birdView.setVisible(True)
        if isEnlarge:
            self.slotTBtnEnlarge()
        else:
            self.slotTBtnNarrow()

    def slotTBtnAIAnalysis(self):
        '''
        AI智能分析点击槽函数
        :return:
        '''
        self.ui.tBtnAIAnalysis.setChecked(True)
        self.hideBtnSetting()
        # 显示上方工具栏对应设置
        self.ui.widgetAIAnalysis.setVisible(True)

    def slotTBtnFill(self):
        # t_img = ImageQt.fromqpixmap(self.MainGraphicsView.microImg)
        # t_metrix = np.array(self.t_img)
        waitingWin = WaitingWin(False, '正在进行小区域填充，请稍等...')
        waitingWin.show()
        labelList = self.MainGraphicsView.getLabelList()
        _label = None
        for label in labelList:
            # and label.origimg == self.MainGraphicsView.microImg
            if isinstance(label, ScrawLabel) and label.type == self.MainGraphicsView.current_type and type(label) == ScrawLabel:
                _label = label
                break
        if _label is None:
            return
        metrix = np.array(Image.fromqpixmap(_label.getPixmap()))
        img_gray = metrix[:, :, 0] * 0.299 + metrix[:, :, 1] * 0.587 + metrix[:, :, 2] * 0.114
        img_gray = img_gray == 0
        import skimage
        img_gray = skimage.morphology.remove_small_objects(img_gray, min_size=40000, connectivity=2)
        img_fill = ~img_gray
        img_fill = np.array(img_fill, dtype=np.uint8)

        res_img = np.zeros((img_fill.shape[0], img_fill.shape[1], 4), dtype=np.uint8)
        if _label.hover:
            res_img[img_fill > 0, :] = np.hstack((_label.backColor.getRgb()[:3], _label.alphaSelect))
        else:
            res_img[img_fill > 0, :] = np.hstack((_label.backColor.getRgb()[:3], _label.alpha))

        im = Image.fromarray(res_img)
        im = im.toqpixmap()
        _label.pixmap = im
        waitingWin.close()

    def slotTBtnRuler(self):
        self.hideBtnSetting()
        self.RulerLabel()
        self.birdView.setVisible(False)

    def slotTBtnIntelligentScissors(self):
        self.intelligentScissors()
        self.birdView.setVisible(False)
        self.ui.PointNumSlider.setVisible(True)
        self.ui.PointNum.setVisible(True)
        self.ui.ScissorsArea.setVisible(True)
        self.ui.ScissorsAreaSlider.setVisible(True)
        self.ui.tBtnOriginPolygonLabel.setChecked(False)
        self.ui.tBtnIntelligentScissors.setChecked(True)

    def handTool(self):
        '''
        手性按钮
        '''
        if self.fileList == []:
            return
        self.MainGraphicsView.initState()
        self.MainGraphicsView.handTool = True
        self.MainGraphicsView.birdViewShow = True
        self.MainGraphicsView.setDragMode(QGraphicsView.ScrollHandDrag)
        self.MainGraphicsView.setCursor(Qt.OpenHandCursor)
        self.MainGraphicsView.changeZoomMode(zoomMode.NoZoom)
        self.MainGraphicsView.viewport().update()

    def arrowTool(self):
        '''
        箭头按钮
        '''
        if self.fileList == []:
            return
        self.MainGraphicsView.initState()
        self.MainGraphicsView.setLabelsInteract(True)
        self.MainGraphicsView.setDragMode(QGraphicsView.RubberBandDrag)
        self.MainGraphicsView.setCursor(Qt.ArrowCursor)
        self.MainGraphicsView.viewport().update()

    def zoomTool(self):
        '''
        放大按钮
        '''
        if self.fileList == []:
            return

        self.MainGraphicsView.initState()
        self.MainGraphicsView.birdViewShow = True
        self.MainGraphicsView.setDragMode(QGraphicsView.NoDrag)
        self.MainGraphicsView.changeZoomMode(zoomMode.ZoomIn)
        self.MainGraphicsView.viewport().update()

    def magnifyTool(self):
        '''
        弃用
        '''
        if self.fileList == []:
            return
        self.MainGraphicsView.initState()
        self.MainGraphicsView.birdViewShow = True
        self.MainGraphicsView.setCursor(Qt.ArrowCursor)
        self.MainGraphicsView.setDragMode(QGraphicsView.ScrollHandDrag)
        self.MainGraphicsView.viewport().update()

    def rectangleLabel(self):
        '''
        矩形标注
        '''
        if len(self.project.classes) == 0:
            dlg = Dialog('请先在编辑-设定目标类型中设置标签')
            dlg.exec()
            self.ui.tBtnArrow.click()
            return
        elif len(self.fileList) == 0:
            dlg = Dialog('请先添加图片')
            dlg.exec()
            self.ui.tBtnArrow.click()
            return
        self.MainGraphicsView.initState()
        self.MainGraphicsView.allowRect = True
        self.MainGraphicsView.setDragMode(QGraphicsView.NoDrag)
        self.MainGraphicsView.changeZoomMode(zoomMode.NoZoom)
        self.MainGraphicsView.setCursor(Qt.CrossCursor)

    def polygonLabel(self):
        '''
        多边形标注
        '''
        if len(self.project.classes) == 0:
            dlg = Dialog('请先在编辑-设定目标类型中设置标签')
            dlg.exec()
            self.ui.tBtnArrow.click()
            return
        elif len(self.fileList) == 0:
            dlg = Dialog('请先添加图片')
            dlg.exec()
            self.ui.tBtnArrow.click()
            return
        self.MainGraphicsView.initState()
        self.MainGraphicsView.allowPolygon = True
        self.MainGraphicsView.setDragMode(QGraphicsView.NoDrag)
        self.MainGraphicsView.changeZoomMode(zoomMode.NoZoom)
        self.MainGraphicsView.setCursor(Qt.CrossCursor)

    def lineLabel(self):
        '''
        线形标注
        '''
        if len(self.project.classes) == 0:
            dlg = Dialog('请先在编辑-设定目标类型中设置标签')
            dlg.exec()
            self.ui.tBtnArrow.click()
            return
        elif len(self.fileList) == 0:
            dlg = Dialog('请先添加图片')
            dlg.exec()
            self.ui.tBtnArrow.click()
            return
        self.MainGraphicsView.initState()
        self.MainGraphicsView.allowLine = True
        self.MainGraphicsView.setCursor(Qt.CrossCursor)
        self.MainGraphicsView.setDragMode(QGraphicsView.NoDrag)
        self.MainGraphicsView.changeZoomMode(zoomMode.NoZoom)

    def pointLabel(self):
        '''
        点标注
        '''
        if len(self.project.classes) == 0:
            dlg = Dialog('请先在编辑-设定目标类型中设置标签')
            dlg.exec()
            self.ui.tBtnArrow.click()
            return
        elif len(self.fileList) == 0:
            dlg = Dialog('请先添加图片')
            dlg.exec()
            self.ui.tBtnArrow.click()
            return
        self.MainGraphicsView.initState()
        self.MainGraphicsView.allowPoint = True
        self.MainGraphicsView.magnifying = True
        self.MainGraphicsView.changeMagnify(True)
        self.MainGraphicsView.setCursor(Qt.CrossCursor)
        self.MainGraphicsView.setDragMode(QGraphicsView.NoDrag)
        self.MainGraphicsView.changeZoomMode(zoomMode.NoZoom)

    def tagLabel(self):
        '''
        标签标注
        '''
        if len(self.project.classes) == 0:
            dlg = Dialog('请先在编辑-设定目标类型中设置标签')
            dlg.exec()
            self.ui.tBtnArrow.click()
            return
        elif len(self.fileList) == 0:
            dlg = Dialog('请先添加图片')
            dlg.exec()
            self.ui.tBtnArrow.click()
            return
        self.MainGraphicsView.initState()
        self.MainGraphicsView.allowTag = True
        self.MainGraphicsView.setCursor(Qt.CrossCursor)
        self.MainGraphicsView.setDragMode(QGraphicsView.NoDrag)
        self.MainGraphicsView.changeZoomMode(zoomMode.NoZoom)

    def circleLabel(self):
        '''
        圆形标注
        '''
        if len(self.project.classes) == 0:
            dlg = Dialog('请先在编辑-设定目标类型中设置标签')
            dlg.exec()
            self.ui.tBtnArrow.click()
            return
        elif len(self.fileList) == 0:
            dlg = Dialog('请先添加图片')
            dlg.exec()
            self.ui.tBtnArrow.click()
            return
        self.MainGraphicsView.initState()
        self.MainGraphicsView.allowCircle = True
        self.MainGraphicsView.setDragMode(QGraphicsView.NoDrag)
        self.MainGraphicsView.setCursor(Qt.CrossCursor)
        self.MainGraphicsView.changeZoomMode(zoomMode.NoZoom)

    def scrawLabel(self):
        '''
        涂鸦标注
        '''
        if len(self.project.classes) == 0:
            dlg = Dialog('请先在编辑-设定目标类型中设置标签')
            dlg.exec()
            self.ui.tBtnArrow.click()
            return
        elif len(self.fileList) == 0:
            dlg = Dialog('请先添加图片')
            dlg.exec()
            self.ui.tBtnArrow.click()
            return
        self.MainGraphicsView.initState()
        self.MainGraphicsView.allowScraw = True
        self.MainGraphicsView.changeScrawMode(True)
        self.MainGraphicsView.setCursor(Qt.CrossCursor)
        self.MainGraphicsView.setDragMode(QGraphicsView.NoDrag)
        self.MainGraphicsView.changeZoomMode(zoomMode.NoZoom)
        if self.ui.tBtnScrawBrushmode.isChecked():
            self.SwitchScrawBrushmode()
        elif self.ui.tBtnScrawErasermode.isChecked():
            self.SwitchScrawErasemode()

    def rectangleCut(self):
        '''
        矩形裁剪
        '''
        self.MainGraphicsView.initState()
        self.MainGraphicsView.allowRectCut = True
        self.MainGraphicsView.setDragMode(QGraphicsView.NoDrag)
        self.MainGraphicsView.changeZoomMode(zoomMode.NoZoom)
        self.MainGraphicsView.setCursor(Qt.CrossCursor)

    def RulerLabel(self):
        self.MainGraphicsView.initState()
        self.MainGraphicsView.allowRuler = True
        self.MainGraphicsView.magnifying = True
        self.MainGraphicsView.changeMagnify(True)
        self.MainGraphicsView.setCursor(Qt.CrossCursor)
        self.MainGraphicsView.setDragMode(QGraphicsView.NoDrag)
        self.MainGraphicsView.changeZoomMode(zoomMode.NoZoom)

    def intelligentScissors(self):
        '''
        磁铁标注
        '''
        if len(self.project.classes) == 0:
            # dlg = Dialog('请先在编辑-设定目标类型中设置标签')
            # dlg.exec()
            self.ui.tBtnArrow.click()
            return
        elif len(self.fileList) == 0:
            # dlg = Dialog('请先添加图片')
            # dlg.exec()
            self.ui.tBtnArrow.click()
            return
        self.MainGraphicsView.initState()
        self.MainGraphicsView.allowIntelligentScissors = True
        self.MainGraphicsView.setDragMode(QGraphicsView.RubberBandDrag)
        self.MainGraphicsView.changeZoomMode(zoomMode.NoZoom)
        self.MainGraphicsView.setCursor(Qt.CrossCursor)

    def Aiscraw(self):
        '''
        智能标注下的涂鸦标注
        '''
        if len(self.project.classes) == 0:
            dlg = Dialog('请先在编辑-设定目标类型中设置标签')
            dlg.exec()
            self.ui.tBtnArrow.click()
            return
        elif len(self.fileList) == 0:
            dlg = Dialog('请先添加图片')
            dlg.exec()
            self.ui.tBtnArrow.click()
            return
        self.MainGraphicsView.allowAiScraw = True
        self.MainGraphicsView.changeScrawMode(True)
        self.MainGraphicsView.setCursor(Qt.CrossCursor)
        self.MainGraphicsView.setDragMode(QGraphicsView.NoDrag)
        self.MainGraphicsView.changeZoomMode(zoomMode.NoZoom)


    def AIMagic(self):
        if len(self.project.classes) == 0:
            dlg = Dialog('请先在编辑-设定目标类型中设置标签')
            dlg.exec()
            self.ui.tBtnArrow.click()
            return
        elif len(self.fileList) == 0:
            dlg = Dialog('请先添加图片')
            dlg.exec()
            self.ui.tBtnArrow.click()
            return
        self.MainGraphicsView.initState()
        self.MainGraphicsView.changeScrawMode(False)
        self.MainGraphicsView.setCursor(Qt.CrossCursor)
        self.MainGraphicsView.setDragMode(QGraphicsView.RubberBandDrag)
        self.MainGraphicsView.changeZoomMode(zoomMode.NoZoom)
        self.MainGraphicsView.allowAIMagic = True
        self.MainGraphicsView.load_efficientvit_model()
        if self.MainGraphicsView.brushflag:
            self.ui.tBtnClickmode.setChecked(True)
            self.MainGraphicsView.brushflag = False
            self.SwitchClickmodeon()
            return
        elif self.MainGraphicsView.Hovermode:
            self.ui.tBtnClickmode.setChecked(True)
            self.SwitchClickmodeon()
            # self.MainGraphicsView.startHoverTimer()
            return
        #  todo 考虑如何实现点击后不重新初始化、按照顺序执行线程

    def changeAILabel(self):
        for item in self.project.toolButtons:
            if item['name'] == '魔术棒' and item['activate']:
                self.ui.tBtnAIMagic.click()
                break

    def endPaint(self):
        self.handTool()

    '''
        标注格式转换与保存
    '''

    def saveTransferObjectDetection(self):
        dist_dir = QFileDialog.getExistingDirectory(self, "选择导出文件夹")
        dist_dict = {
            "info": {
                "description": "",
                "url": "",
                "version": "",
                "year": time.localtime().tm_year,
                "contributor": "",
                "date_created": time.strftime("%Y-%m-%d", time.localtime())
            },
            "licenses": [
                {
                    "id": 1,
                    "name": None,
                    "url": None
                }
            ],
            "categories": [
            ],
            "images": [
            ],
            "annotations": [
            ]
        }

        image_count = 1
        type_count = 1
        current_type = []

        for path in self.getFileList():

            filedir, tempfilename = os.path.split(path)
            shotname, extension = os.path.splitext(tempfilename)

            label_path = os.path.join(filedir, shotname + ".json")
            if os.path.isfile(label_path):
                with open(label_path, 'r', encoding='utf-8') as file_obj:
                    dict = json.load(file_obj)
                    typeList = dict["classification"]
                    new_image_dict = {
                        "file_name": tempfilename,
                        "height": dict["image_height"],
                        "width": dict["image_width"],
                        "date_captured": time.strftime("%Y-%m-%d", time.localtime(os.path.getatime(path))),
                        "id": image_count,
                        "license": 1,
                        "color_url": "",
                        "flickr_url": ""
                    }

                    for type in typeList:
                        if type not in current_type:
                            new_type_dict = {
                                "id": type_count,
                                "name": type,
                                "supercategory": "None"
                            }
                            dist_dict["categories"].append(new_type_dict)
                            type_count += 1
                            current_type.append(type)

                    dist_dict["images"].append(new_image_dict)

                    label_count = 1

                    for label in dict["image_object_detection"]:
                        t_type = label["label_type"]

                        if label["label_class"] == "Rectangle":

                            new_label_dict = {
                                "id": int(str(image_count) + str(label_count).zfill(4)),
                                "image_id": image_count,
                                "category_id": current_type.index(t_type) + 1,
                                "iscrowd": 0,
                                "area": label["width"] * label["height"],
                                "bbox": [
                                    label["left"],
                                    label["top"],
                                    label["width"],
                                    label["height"]
                                ]
                            }
                            dist_dict["annotations"].append(new_label_dict)
                            label_count += 1


                        else:
                            pass
                    image_count += 1

        with open(os.path.join(dist_dir, "label.json"), "w", encoding="utf-8") as file_obj:
            json.dump(dist_dict, file_obj, indent=4, ensure_ascii=False)

    def saveTransferPNG(self):
        # dist_dir = QFileDialog.getExistingDirectory(self, "选择导出文件夹")
        dist_dir = self.project.labeledDataDir
        # os.makedirs(os.path.join(dist_dir, "labels"))
        for path in self.getFileList():
            filedir, tempfilename = os.path.split(path)
            shotname, extension = os.path.splitext(tempfilename)

            label_path = os.path.join(filedir, shotname + ".json")
            if os.path.isfile(label_path):

                with open(label_path, 'r', encoding='utf-8') as file_obj:
                    dict = json.load(file_obj)
                    typeList = dict["classification"]
                    type_num = len(typeList)

                    grey_scale_list = [i for i in range(0, 256, int(255 / type_num))]

                    pixmap = QPixmap(dict["image_height"], dict["image_width"])
                    p = QPainter()
                    p.begin(pixmap)
                    p.setPen(Qt.NoPen)
                    brush = QBrush(Qt.SolidPattern)

                    if not os.path.isfile(os.path.join(dist_dir, "label.json")):
                        with open(os.path.join(dist_dir, "label.json"), 'w', encoding='utf-8') as _file_obj:
                            typeDict = {
                                'background': 0
                            }
                            for type in typeList:
                                typeDict[type] = grey_scale_list[typeList.index(type) + 1]
                            json.dump(typeDict, _file_obj, indent=4, ensure_ascii=False)

                    for label in dict["image_object_detection"]:
                        t_type = label["label_type"]
                        current_grey_color = grey_scale_list[typeList.index(t_type) + 1]
                        brush.setColor(QColor(current_grey_color, current_grey_color, current_grey_color))
                        p.setBrush(brush)

                        if label["label_class"] == "Rectangle":

                            p.drawRect(QRectF(label["left"],
                                              label["top"],
                                              label["width"],
                                              label["height"]))

                        elif label["label_class"] == "Polygon" or label["label_class"] == "Line":

                            point_list = []
                            for point in label["point_list"]:
                                point_list.append(QPoint(*point))
                            p.drawPolygon(QPolygonF(point_list))
                        elif label["label_class"] == "Scraw":

                            byteArray = base64.b64decode(label["label_png"])
                            _pixmap = QPixmap()
                            _pixmap.loadFromData(byteArray, "png")
                            arr = np.array(Image.fromqpixmap(_pixmap))
                            dist = np.zeros(arr.shape, dtype=np.uint8)
                            arr = arr.sum(axis=2)

                            dist[arr > 0, :] = np.hstack(
                                (QColor(current_grey_color, current_grey_color, current_grey_color).getRgb()[:3], 255))

                            im = Image.fromarray(dist)
                            im = im.toqpixmap()

                            p.drawPixmap(QRect(0, 0,
                                               pixmap.width(),
                                               pixmap.height()), im)
                        else:
                            pass

                p.end()
                image = ImageQt.fromqpixmap(pixmap)
                array = np.array(image)
                array = array[:, :, 0]
                image = Image.fromarray(array, mode='L')
                image.save(os.path.join(dist_dir, "labels", shotname + ".png"))

    def saveImg(self, filepath):
        t_img = ImageQt.fromqpixmap(self.MainGraphicsView.microImg)
        t_metrix = np.array(t_img)

    def save(self, filepath):
        print("change saving:", filepath)
        filedir, tempfilename = os.path.split(filepath)
        shotname, extension = os.path.splitext(tempfilename)

        distpath = os.path.join(self.project.labeledDataDir, shotname + ".json")

        rawImage = Image.open(filepath)
        imgHeight = rawImage.height
        imgWidth = rawImage.width

        dict = {}
        dict["version"] = self.config.version
        dict["file_path"] = filepath
        dict["classification"] = [_class["id"] for _class in self.project.classes]
        # dict["classificationColor"] = [dict(_class["type"], _class["color"]) for _class in self.project.classes]

        dict["image_height"] = imgHeight
        dict["image_width"] = imgWidth
        # dict["image_height"] = self.MainGraphicsView.microImg.height()
        # dict["image_width"] = self.MainGraphicsView.microImg.width()
        # dict["status"] = self.getStausList()[self.ui.listWidgetFile.currentRow()]

        polygonLabels = []
        labelList = self.MainGraphicsView.getLabelList()
        for label in labelList:
            if label.labelClass == "preseg_scraw" or label.labelClass == "RectCut":
                continue
            temp_Export = label.getExport()
            temp_Export["label_type"] = self.project.getIdByType(temp_Export["label_type"])
            polygonLabels.append(temp_Export)

        dict["image_object_detection"] = polygonLabels

        with open(os.path.join(self.project.labeledDataDir, distpath), 'w', encoding='utf-8') as file_obj:
            json.dump(dict, file_obj, indent=4, ensure_ascii=False)

    def closeEvent(self, *args, **kwargs):
        try:
            self.save(self.fileList[self.lastFileIndex].get('path'))
        except Exception as e:
            logging.error("[wins.main.closeEvent] {}".format(e))

    def labelCreatingLock(self, isFinished):
        if isFinished:
            self.ui.comboBoxTags.setEnabled(True)
            self.ui.labelPartitionColor.setEnabled(True)
            self.ui.listwidgetFile.setEnabled(True)
            self.MainGraphicsView.undoAction.setEnabled(True)
            self.MainGraphicsView.redoAction.setEnabled(True)
            self.ui.tBtnFill.setEnabled(True)
            self.ui.tBtnToPolygonLabel.setEnabled(True)
            self.ui.tBtnToScrawLabel.setEnabled(True)
            self.ui.toolButtonHome.setEnabled(True)
            self.ui.pBtnLogin.setEnabled(True)
            self.ui.widgetPolygon.setEnabled(True)
            # 编辑
            self.action_partition_label.setEnabled(True)
            self.action_keep_label.setEnabled(True)
            self.action_keep_size.setEnabled(True)
            # 文件
            self.actionImportNewData.setEnabled(True)
            self.actionImportNewDataAndLabel.setEnabled(True)
            self.actionLastImg.setEnabled(True)
            self.actionNextImg.setEnabled(True)
            self.actionExportLabel.setEnabled(True)
            self.actionDeleteImgAndLabel.setEnabled(True)
            self.actionDeleteAllImgAndLabel.setEnabled(True)
            self.actionDeleteLabel.setEnabled(True)
            self.actionDeleteAllLabel.setEnabled(True)
            self.actionDeleteNoLabelImg.setEnabled(True)
            self.actionBackHome.setEnabled(True)
            self.actionExit.setEnabled(True)
            # 图像
            self.actionReversed.setEnabled(True)
            self.actionBrightnessContrast.setEnabled(True)
            self.actionImgCrop.setEnabled(True)
            self.actionAnyangle.setEnabled(True)
            self.actionDNinty.setEnabled(True)
            self.actionNintyRW.setEnabled(True)
            self.actionNinty.setEnabled(True)
            self.actionFlipH.setEnabled(True)
            self.actionFlipV.setEnabled(True)
            self.actionEnhancedReset.setEnabled(True)
            self.menuRuler.setEnabled(True)
            # 标注
            self.actionHistogramAdjustments.setEnabled(True)
            self.actionThresholdSegmentation.setEnabled(True)
            self.createRectangleLabel.setEnabled(True)
            self.createPolygonLabel.setEnabled(True)
            self.createPointLabel.setEnabled(True)
            self.createLineLabel.setEnabled(True)
            self.createBrushLabel.setEnabled(True)
            self.createAILabel.setEnabled(True)
            self.Hand.setEnabled(True)
            self.Edit.setEnabled(True)
            self.ToPolygonLabel.setEnabled(True)
            self.ToScrawLabel.setEnabled(True)
            self.ToScrawLabel.setEnabled(True)
            self.ScrawFill.setEnabled(True)
            self.actionLabelDisplay.setEnabled(True)
            self.actionStatisticalAnalysis.setEnabled(True)
            # 视图
            self.actionEnlarge.setEnabled(True)
            self.actionNarrow.setEnabled(True)
            self.actionFitScreen.setEnabled(True)
            self.action_fill_screen.setEnabled(True)
            # 窗口
            #self.actionFileList.setEnabled(True)
            #self.actionTypeList.setEnabled(True)
            #self.actionStatisticsList.setEnabled(True)
            # 帮助
            self.actionHelp.setEnabled(True)
            self.actionAactivation.setEnabled(True)
            self.actionUpdate.setEnabled(True)
            self.actionAbout.setEnabled(True)
            # 操作栏和统计栏
            self.ui.widgetManipulation.setEnabled(True)
            self.ui.widgetStatistics.setEnabled(True)
            # 工具栏
            self.ui.tBtnHand.setEnabled(True)
            self.ui.tBtnArrow.setEnabled(True)
            self.ui.tBtnZoom.setEnabled(True)
            self.ui.tBtnHand.setEnabled(True)
            self.ui.tBtnRectangleLabel.setEnabled(True)
            self.ui.tBtnPolygonLabel.setEnabled(True)
            self.ui.tBtnBrush.setEnabled(True)
            self.ui.tBtnAIMagic.setEnabled(True)
            # self.ui.tBtnGrabcut.setEnabled(True)
            self.ui.tBtnStatisticalAnalysis.setEnabled(True)
            self.ui.tBtnToolsEdit.setEnabled(True)
            self.ui.tBtnPointLabel.setEnabled(True)
            self.ui.tBtnLine.setEnabled(True)
            self.ui.tBtnCircle.setEnabled(True)
            self.ui.tBtnCollapse.setEnabled(True)
            self.ui.toolButtonChangeRawImg.setEnabled(True)
            # 分页
            self.ui.comboBoxPage.setEnabled(True)
            self.ui.pushButtonFilter.setEnabled(True)
            self.ui.pushButtonSwitch.setEnabled(True)
            self.ui.pushButtonPrePage.setEnabled(True)
            self.ui.pushButtonNextPage.setEnabled(True)
            self.ui.pushButtonHomePage.setEnabled(True)
            self.ui.pushButtonFinalPage.setEnabled(True)
            self.ui.pushButtonPage1.setEnabled(True)
            self.ui.pushButtonPage2.setEnabled(True)
            self.ui.pushButtonPage3.setEnabled(True)

            self.ui.toolButtonSetting.setEnabled(True)
            if hasattr(self,'menuMain'):
                self.menuMain.setEnabled(True)
            if hasattr(self,'menuLabelTable'):
                self.menuLabelTable.setEnabled(True)
        else:
            self.ui.comboBoxTags.setEnabled(False)
            self.ui.labelPartitionColor.setEnabled(False)
            self.ui.listwidgetFile.setEnabled(False)
            self.MainGraphicsView.undoAction.setEnabled(False)
            self.MainGraphicsView.redoAction.setEnabled(False)
            self.ui.tBtnFill.setEnabled(False)
            self.ui.tBtnToPolygonLabel.setEnabled(False)
            self.ui.tBtnToScrawLabel.setEnabled(False)
            self.ui.toolButtonHome.setEnabled(False)
            self.ui.pBtnLogin.setEnabled(False)
            self.ui.widgetPolygon.setEnabled(False)
            # 编辑
            self.action_partition_label.setEnabled(False)
            self.action_keep_label.setEnabled(False)
            self.action_keep_size.setEnabled(False)
            # 文件
            self.actionImportNewData.setEnabled(False)
            self.actionImportNewDataAndLabel.setEnabled(False)
            self.actionLastImg.setEnabled(False)
            self.actionNextImg.setEnabled(False)
            self.actionExportLabel.setEnabled(False)
            self.actionDeleteImgAndLabel.setEnabled(False)
            self.actionDeleteAllImgAndLabel.setEnabled(False)
            self.actionDeleteLabel.setEnabled(False)
            self.actionDeleteAllLabel.setEnabled(False)
            self.actionDeleteNoLabelImg.setEnabled(False)
            self.actionBackHome.setEnabled(False)
            self.actionExit.setEnabled(False)
            # 图像
            self.actionReversed.setEnabled(False)
            self.actionBrightnessContrast.setEnabled(False)
            self.actionImgCrop.setEnabled(False)
            self.actionAnyangle.setEnabled(False)
            self.actionDNinty.setEnabled(False)
            self.actionNintyRW.setEnabled(False)
            self.actionNinty.setEnabled(False)
            self.actionFlipH.setEnabled(False)
            self.actionFlipV.setEnabled(False)
            self.actionEnhancedReset.setEnabled(False)
            self.menuRuler.setEnabled(False)
            # 标注
            self.actionHistogramAdjustments.setEnabled(False)
            self.actionThresholdSegmentation.setEnabled(False)
            self.createRectangleLabel.setEnabled(False)
            self.createPolygonLabel.setEnabled(False)
            self.createPointLabel.setEnabled(False)
            self.createLineLabel.setEnabled(False)
            self.createBrushLabel.setEnabled(False)
            self.createAILabel.setEnabled(False)
            self.Hand.setEnabled(False)
            self.Edit.setEnabled(False)
            self.ToPolygonLabel.setEnabled(False)
            self.ToScrawLabel.setEnabled(False)
            self.ToScrawLabel.setEnabled(False)
            self.ScrawFill.setEnabled(False)
            self.actionLabelDisplay.setEnabled(False)
            self.actionStatisticalAnalysis.setEnabled(False)
            # 视图
            self.actionEnlarge.setEnabled(False)
            self.actionNarrow.setEnabled(False)
            self.actionFitScreen.setEnabled(False)
            self.action_fill_screen.setEnabled(False)
            # 窗口
            #self.actionFileList.setEnabled(False)
            # self.actionTypeList.setEnabled(False)
            # self.actionStatisticsList.setEnabled(False)
            # 帮助
            self.actionHelp.setEnabled(False)
            self.actionAactivation.setEnabled(False)
            self.actionUpdate.setEnabled(False)
            self.actionAbout.setEnabled(False)
            # 操作栏和统计栏
            self.ui.widgetManipulation.setEnabled(False)
            self.ui.widgetStatistics.setEnabled(False)
            # 工具栏
            self.ui.tBtnHand.setEnabled(False)
            self.ui.tBtnArrow.setEnabled(False)
            self.ui.tBtnZoom.setEnabled(False)
            self.ui.tBtnHand.setEnabled(False)
            self.ui.tBtnRectangleLabel.setEnabled(False)
            self.ui.tBtnPolygonLabel.setEnabled(False)
            self.ui.tBtnBrush.setEnabled(False)
            self.ui.tBtnAIMagic.setEnabled(False)
            # self.ui.tBtnGrabcut.setEnabled(False)
            self.ui.tBtnStatisticalAnalysis.setEnabled(False)
            self.ui.tBtnToolsEdit.setEnabled(False)
            self.ui.tBtnPointLabel.setEnabled(False)
            self.ui.tBtnLine.setEnabled(False)
            self.ui.tBtnCircle.setEnabled(False)
            #self.ui.tBtnCollapse.setEnabled(False)
            self.ui.toolButtonChangeRawImg.setEnabled(False)
            # 分页
            self.ui.comboBoxPage.setEnabled(False)
            self.ui.pushButtonFilter.setEnabled(False)
            self.ui.pushButtonSwitch.setEnabled(False)
            self.ui.pushButtonPrePage.setEnabled(False)
            self.ui.pushButtonNextPage.setEnabled(False)
            self.ui.pushButtonHomePage.setEnabled(False)
            self.ui.pushButtonFinalPage.setEnabled(False)
            self.ui.pushButtonPage1.setEnabled(False)
            self.ui.pushButtonPage2.setEnabled(False)
            self.ui.pushButtonPage3.setEnabled(False)

            self.ui.toolButtonSetting.setEnabled(False)
            if hasattr(self,'menuMain'):
                self.menuMain.setEnabled(False)
            if hasattr(self,'menuLabelTable'):
                self.menuLabelTable.setEnabled(False)

    def processImportConflictByMode(self, mode: ConflictMode):
        for i in range(len(self.conflictImportResult)):
            self.conflictImportResult[i]['conflictMode'] = mode
        self.ImportConflict()

    def processImportConflictByUser(self, selectModeList: list):
        for i in range(len(selectModeList)):
            self.conflictImportResult[i]['conflictMode'] = selectModeList[i]
        self.ImportConflict()

    def startProcessImportConflict(self):
        logging.info("self.conflictImportResult={}".format(self.conflictImportResult))
        for item in tqdm(self.conflictImportResult):
            conflictMode = item['conflictMode']
            if conflictMode == ConflictMode.Skip:
                continue
            elif conflictMode == ConflictMode.Replace:
                replaceImageFile = item['labelmeImageFile']
                replaceLabelFile = item['labelmeLabelFile']

                replaceImageName, replaceImageSuffix = os.path.splitext(os.path.basename(replaceImageFile))
                replaceLabelName = replaceImageName + '.json'

                wisImageFile = os.path.join(self.project.rawDataDir, replaceImageName + replaceImageSuffix)
                wisLabelFile = os.path.join(self.project.labeledDataDir, replaceLabelName)

                if os.path.exists(wisLabelFile):
                    with open(wisLabelFile, 'r', encoding='utf-8') as f:
                        dict = json.load(f)
                        for label in dict['image_object_detection']:
                            if label['label_class'] == "Scraw":
                                for cls in self.project.classes:
                                    if label['label_type'] == cls['id'] and cls['scraw'] > 0:
                                        cls['scraw'] -= 1
                            else:
                                for cls in self.project.classes:
                                    if label['label_type'] == cls['id'] and cls['instance'] > 0:
                                        cls['instance'] -= 1
                    os.remove(wisLabelFile)
                if self.project.needResize():
                    for file in glob.iglob(os.path.join(self.project.rawDataDir, replaceImageName+'_*[0-9].json')):
                        os.remove(file)

                self.saveToWisLabelFile(replaceImageFile, replaceLabelFile, wisImageFile, wisLabelFile, item['categoryDict'])

            elif conflictMode == ConflictMode.Coexist:
                coexistImageFile = item['labelmeImageFile']
                coexistLabelFile = item['labelmeLabelFile']

                coexistImageName, coexistImageSuffix = os.path.splitext(os.path.basename(coexistImageFile))
                i = 1
                coexistImageName = coexistImageName + '-'+ str(i)
                while(os.path.isfile(os.path.join(self.project.rawDataDir, coexistImageName + coexistImageSuffix))):
                    i = i + 1
                    coexistImageName = coexistImageName + '-'+ str(i)
                coexistLabelName = coexistImageName + '.json'

                wisImageFile = os.path.join(self.project.rawDataDir, coexistImageName + coexistImageSuffix)
                wisLabelFile = os.path.join(self.project.labeledDataDir, coexistLabelName)
                self.saveToWisLabelFile(coexistImageFile, coexistLabelFile, wisImageFile, wisLabelFile, item['categoryDict'])
        # 冲突处理完成, 更新进度条
        # self.current_num += 1
        self.updateProgressBar(self.total / self.total * 100)

        # 4.修改classification字段
        classification = [_class["id"] for _class in self.project.classes]
        fileList = []
        fileDict = {}
        for ext in ['*']:
            fileList.extend(glob.glob(os.path.join(self.project.labeledDataDir, ext)))
        for file in fileList:
            with open(file, 'r', encoding='utf-8') as file_obj:
                fileDict = json.load(file_obj)
                fileDict['classification'] = classification
            with open(file, 'w', encoding='utf-8') as file_obj:
                json.dump(fileDict, file_obj, indent=4, ensure_ascii=False)

        self.conflictImportResult = []
        self.conflictFileNameList = []

    def saveToWisLabelFile(self, saveImageFile, saveLabelFile, wisImageFile, wisLabelFile, categoryDict, callback=None):
        labelConventor = LabelConventor(self.project.classes)
        width, height = Image.open(saveImageFile).size
        infoList = [saveImageFile, saveLabelFile, wisImageFile, wisLabelFile, width, height]
        labelConventor.imagelabel2wisdom(self.config.version, self.project, infoList, categoryDict, callback)

        self.project.classes = labelConventor.classes

    def set_waiting_win(self, status: bool, info: str = None):
        if status:
            self.waitingWin = WaitingWin(cancelEnable=False)
            if info:
                self.waitingWin.update_tip_info(info)
            self.waitingWin.show()
        else:
            if self.conflictFileNameList:
                logging.info("处理导入文件冲突问题...")
                logging.info('冲突文件数量：{}'.format(len(self.conflictFileNameList)))
                # logging.info("self.conflictImportResult={}".format(self.conflictImportResult))
                self.importConflictWin = ImportConflictDialog(self.conflictFileNameList)
                self.importConflictWin.signalConflictProcessByMode.connect(self.processImportConflictByMode)
                self.importConflictWin.signalConflictProcessByUser.connect(self.processImportConflictByUser)
                self.importConflictWin.show()
            else:
                self.importFinished()

            if self.__dict__.get('waitingWin') and self.waitingWin:
                self.waitingWin.close()
            self.fileList = copy.deepcopy(self.project.importFiles)
            for i in range(len(self.fileList)):  # 相对路径转为绝对路径
                self.fileList[i]['path'] = os.path.join(self.project.rawDataDir, self.fileList[i]['path'])
            # Todo:这里fileList跟project中的importFiles是不是重复了

            self.lastFileIndex = -1
            self.refreshPage(self.currentPage)
            self.updateLabelFileDescription()
            self.project.save()

            if self.project.needResize():
                method, size, mode = self.project.getResizeParam()
                if method == '滑动重叠裁剪':
                    if mode == '0.5':
                        alertOk(self, "成功", "导入图片已按1/2比例裁剪至" + str(size) + '*' + str(size))
                    elif mode == '0.25':
                        alertOk(self, "成功", "导入图片已按1/4比例裁剪至" + str(size) + '*' + str(size))
                    elif mode == '0.0':
                        alertOk(self, "成功", "导入图片已无重叠裁剪至" + str(size) + '*' + str(size))
                elif method == '比例缩放':
                    if mode == 'equal':
                        alertOk(self, "成功", "导入图片已等比例缩放至" + str(size) + '*' + str(size))
                    elif mode == 'width':
                        alertOk(self, "成功", "导入图片已按横边缩放至" + str(size) + '*' + str(size))
                    elif mode == 'height':
                        alertOk(self, "成功", "导入图片已按纵边缩放至" + str(size) + '*' + str(size))
        return True

    def Export(self, isAllLabel, extype, expath, flagIncludeInfer, thresholdValue): # bool, str, str, bool, float
        self.exportWin.hide()
        self.calculateWin.ui.labelCalculateHandleTitle.setText(i18n['label_exporting'])
        self.calculateWin.ui.labelTitle.setText(i18n['label_export'])
        self.calculateWin.ui.progressBar.setValue(0)
        self.calculateWin.ui.pBtnCancel.setText('关闭提示')
        self.calculateWin.ui.pBtnOpenResult.setText('打开结果')
        self.calculateWin.ui.pBtnOpenResult.clicked.disconnect()
        self.calculateWin.ui.pBtnOpenResult.clicked.connect(lambda: openFolder(expath))
        self.calculateWin.ui.pBtnCancel.clicked.connect(lambda: self.calculateWin.close())
        self.calculateWin.ui.pBtnOpenResult.hide()
        self.calculateWin.ui.pBtnCancel.hide()
        self.calculateWin.show()
        QApplication.processEvents() #强制立即执行上述的ui操作

        self.save(self.fileList[self.ui.listwidgetFile.currentRow() + self.pageSize * (self.currentPage-1)].get('path'))

        args = dict(
                isAllLabel=isAllLabel,
                exportType=extype,
                exportPath=expath,
                flagIncludeInfer=flagIncludeInfer,
                thresholdValue=thresholdValue
            )
        # self.set_waiting_win(True, "正在导出数据...")
        self.exportThread = CalculationThread(self.ExportLabel, args)
        self.exportThread.signal_finished.connect(
            lambda flag: self.exportFinished() if flag else print('任务出错了'))
        self.exportThread.signal_progress_update.connect(self.updateProgressBar)
        self.exportThread.signal_error.connect(lambda msg: self.show_error_and_close_win(msg, i18n['label_export_failed']))
        self.exportThread.start()
        # self.ExportLabel(isAllLabel, extype, expath)

    def show_error_and_close_win(self, msg, title):
        self.calculateWin.close()
        alertError(self, i18n['tip'], title, msg)

    def exportFinished(self):
        # self.set_waiting_win(False)
        self.calculateWin.ui.labelCalculateHandleTitle.setText(i18n['label_export_finished'])
        self.calculateWin.ui.pBtnOpenResult.setCursor(QtGui.QCursor(Qt.PointingHandCursor))
        self.calculateWin.ui.pBtnCancel.setCursor(QtGui.QCursor(Qt.PointingHandCursor))
        self.calculateWin.ui.pBtnOpenResult.show()
        self.calculateWin.ui.pBtnCancel.show()

    def updateProgressBar(self, value):
        self.calculateWin.ui.progressBar.setValue(value)


    def AutoSearch(self, rawDataDir):
        self.calculateWin.ui.labelCalculateHandleTitle.setText(i18n['data_importing'])
        self.calculateWin.ui.labelTitle.setText(i18n['data_import'])
        self.calculateWin.ui.progressBar.setValue(0)
        self.calculateWin.ui.pBtnOpenResult.setText('确定')
        self.calculateWin.ui.pBtnOpenResult.clicked.disconnect()
        self.calculateWin.ui.pBtnOpenResult.clicked.connect(lambda: self.calculateWin.close())
        self.calculateWin.ui.pBtnOpenResult.setCursor(QtGui.QCursor(Qt.PointingHandCursor))
        self.calculateWin.ui.pBtnOpenResult.hide()
        self.calculateWin.ui.pBtnCancel.hide()
        self.calculateWin.show()

        args = dict(
                rawDataDir=rawDataDir
            )
        # self.set_waiting_win(True, "正在导入数据...")
        self.autoSearchThread = CalculationThread(self.AutoSearchNewImageAndLabel, args, True)
        self.autoSearchThread.signal_finished.connect(
            # lambda flag: self.set_waiting_win(False) if flag else print('任务出错了'))
            lambda flag: self.set_waiting_win(False) if flag else print('任务出错了'))
        self.autoSearchThread.signal_progress_update.connect(lambda value: self.updateProgressBar(value))
        self.autoSearchThread.signal_error.connect(lambda msg: self.show_error_and_close_win(msg, i18n['data_import_failed']))
        self.autoSearchThread.start()
        # self.AutoSearchNewImageAndLabel(rawDataDir)

    def DIYRule(self, imageDir, labelDir, imageName, labelName,
                      imageSuffix, labelSuffix, backgroundIndex):
        self.calculateWin.ui.labelCalculateHandleTitle.setText(i18n['data_importing'])
        self.calculateWin.ui.labelTitle.setText(i18n['data_import'])
        self.calculateWin.ui.progressBar.setValue(0)
        self.calculateWin.ui.pBtnOpenResult.setText('确定')
        self.calculateWin.ui.pBtnOpenResult.clicked.disconnect()
        self.calculateWin.ui.pBtnOpenResult.clicked.connect(lambda: self.calculateWin.close())
        self.calculateWin.ui.pBtnOpenResult.setCursor(QtGui.QCursor(Qt.PointingHandCursor))
        self.calculateWin.ui.pBtnCancel.hide()
        self.calculateWin.ui.pBtnOpenResult.hide()
        self.calculateWin.show()

        # self.set_waiting_win(True, "正在导入数据...")
        args = dict(
                imageDir=imageDir,
                labelDir=labelDir,
                imageName=imageName,
                labelName=labelName,
                imageSuffix=imageSuffix,
                labelSuffix=labelSuffix,
                backgroundIndex=backgroundIndex
            )
        self.diyRuleThread = CalculationThread(self.DIYRuleNewImageAndLabel, args, True)
        self.diyRuleThread.signal_finished.connect(
            lambda flag: self.set_waiting_win(False) if flag else print('任务出错了'))
        self.diyRuleThread.signal_progress_update.connect(lambda value: self.updateProgressBar(value))
        self.diyRuleThread.signal_error.connect(lambda msg: self.show_error_and_close_win(msg, i18n['data_import_failed']))
        self.diyRuleThread.start()

    def importFinished(self):
        # self.set_waiting_win(False)
        self.calculateWin.ui.labelCalculateHandleTitle.setText(i18n['data_import_finished'])
        self.calculateWin.ui.pBtnOpenResult.show()

    def ImportConflict(self):
        # self.set_waiting_win(True, "正在处理冲突...")
        self.importconfilctThread = CalculationThread(self.startProcessImportConflict, {})
        self.importconfilctThread.signal_finished.connect(
            lambda flag: self.set_waiting_win(False) if flag else print('任务出错了'))
        self.importconfilctThread.signal_error.connect(
            lambda msg: self.show_error_and_close_win(msg, i18n['data_import_failed']))
        self.importconfilctThread.start()

    def ExportLabel(self, isAllLabel, exportType, exportPath, flagIncludeInfer, thresholdValue):
        count = 0
        if isAllLabel:
            for file in self.fileList:
                imagePath = file['path']
                basename = os.path.basename(imagePath)
                mainname = basename.split('.')[0]
                labelPath =  os.path.join(self.project.labeledDataDir, mainname+'.json')
                if os.path.exists(exportPath) and os.path.exists(labelPath):
                    shutil.copy(imagePath, exportPath)
                    if file['inferCompleted'] and flagIncludeInfer or file['labelCompleted']:
                        labelConventor = LabelConventor(self.project.classes)
                        with open(labelPath, 'r', encoding='utf-8') as jf:
                            labelDict = json.load(jf)
                            if exportType == 'wisdom':
                                with open(os.path.join(exportPath, mainname+'.json'), 'w', encoding='utf-8') as file_obj:
                                    json.dump(labelDict, file_obj, indent=4, ensure_ascii=False)
                            elif exportType == 'labelme':
                                newDict = {}
                                newDict["version"] = "5.1.0"
                                newDict["flags"] = {}
                                newDict["shapes"] = labelConventor.wisdom2labelme(labelDict, thresholdValue, file['inferCompleted'])
                                newDict["imagePath"] = imagePath
                                with open(imagePath, "rb") as img:
                                    encoded = str(base64.b64encode(img.read()), encoding='utf-8')
                                    newDict["imageData"] = encoded
                                newDict["imageHeight"] = labelDict["image_height"]
                                newDict["imageWidth"] = labelDict["image_width"]
                                with open(os.path.join(exportPath, mainname+'.json'), 'w', encoding='utf-8') as file_obj:
                                    json.dump(newDict, file_obj, indent=4, ensure_ascii=False)
                            elif exportType == 'yolo':
                                shapeList = labelConventor.wisdom2yolo(labelDict, thresholdValue, file['inferCompleted'])
                                if shapeList:
                                    with open(os.path.join(exportPath, mainname+'.txt'), 'w', encoding='utf-8') as file_obj:
                                        for shape in shapeList:
                                            shape_str = ' '.join(shape)
                                            file_obj.writelines(shape_str + '\n')
                                categoryDict = {}
                                for wisclass in self.project.classes:
                                    categoryDict[int(wisclass['id'])] = wisclass['type']
                                with open(os.path.join(exportPath, 'classes.txt'), 'w', encoding='utf-8') as file_obj:
                                    for key in categoryDict:
                                        file_obj.write(str(key)+" "+str(categoryDict[key]+"\n"))
                            elif exportType == 'mask':
                                mask = np.zeros((int(labelDict["image_height"]), int(labelDict["image_width"]), 3), dtype=np.uint8)
                                maskDict = labelConventor.wisdom2mask(labelDict, thresholdValue, file['inferCompleted'])
                                for wisclass in self.project.classes[::-1]:
                                    if wisclass["id"] in maskDict:
                                        for labelmask in maskDict[wisclass["id"]]:
                                            filtered = (labelmask[:, :, 0]!=0)|(labelmask[:, :, 1]!=0)|(labelmask[:, :, 2]!=0)
                                            mask[:, :, 0] = np.where(filtered, labelmask[:, :, 0], mask[:, :, 0])
                                            mask[:, :, 1] = np.where(filtered, labelmask[:, :, 1], mask[:, :, 1])
                                            mask[:, :, 2] = np.where(filtered, labelmask[:, :, 2], mask[:, :, 2])
                                if mask.max() != 0:
                                    im = Image.fromarray(mask)
                                    im.save(os.path.join(exportPath, mainname+'_label.png'))
                count = count + 1
                self.updateProgressBar(count / len(self.fileList) * 100)
        else:
            rowIndex = self.ui.listwidgetFile.currentRow() + self.pageSize * (self.currentPage - 1)
            imagePath = self.fileList[rowIndex]['path']
            basename = os.path.basename(imagePath)
            mainname = basename.split('.')[0]
            labelPath =  os.path.join(self.project.labeledDataDir, mainname+'.json')
            if os.path.exists(exportPath) and os.path.exists(labelPath):
                shutil.copy(imagePath, exportPath)
                if self.fileList[rowIndex]['inferCompleted'] and flagIncludeInfer or self.fileList[rowIndex]['labelCompleted']:
                    labelConventor = LabelConventor(self.project.classes)
                    with open(labelPath, 'r', encoding='utf-8') as jf:
                        labelDict = json.load(jf)
                        if exportType == 'wisdom':
                            with open(os.path.join(exportPath, mainname+'.json'), 'w', encoding='utf-8') as file_obj:
                                json.dump(labelDict, file_obj, indent=4, ensure_ascii=False)
                        elif exportType == 'labelme':
                            newDict = {}
                            newDict["version"] = "5.1.0"
                            newDict["flags"] = {}
                            newDict["shapes"] = labelConventor.wisdom2labelme(labelDict, thresholdValue, self.fileList[rowIndex]['inferCompleted'])
                            newDict["imagePath"] = imagePath
                            with open(imagePath, "rb") as img:
                                encoded = str(base64.b64encode(img.read()), encoding='utf-8')
                                newDict["imageData"] = encoded
                            newDict["imageHeight"] = labelDict["image_height"]
                            newDict["imageWidth"] = labelDict["image_width"]
                            with open(os.path.join(exportPath, mainname+'.json'), 'w', encoding='utf-8') as file_obj:
                                json.dump(newDict, file_obj, indent=4, ensure_ascii=False)
                        elif exportType == 'yolo':
                            shapeList = labelConventor.wisdom2yolo(labelDict, thresholdValue, self.fileList[rowIndex]['inferCompleted'])
                            with open(os.path.join(exportPath, mainname+'.txt'), 'w', encoding='utf-8') as file_obj:
                                for shape in shapeList:
                                    shape_str = ' '.join(shape)
                                    file_obj.writelines(shape_str + '\n')
                            categoryDict = {}
                            for wisclass in self.project.classes:
                                categoryDict[int(wisclass['id'])] = wisclass['type']
                            with open(os.path.join(exportPath, 'classes.txt'), 'w', encoding='utf-8') as file_obj:
                                for key in categoryDict:
                                    file_obj.write(str(key)+" "+str(categoryDict[key]+"\n"))
                        elif exportType == 'mask':
                            mask = np.zeros((int(labelDict["image_height"]), int(labelDict["image_width"]), 3), dtype=np.uint8)
                            maskDict = labelConventor.wisdom2mask(labelDict, thresholdValue, self.fileList[rowIndex]['inferCompleted'])
                            for wisclass in self.project.classes[::-1]:
                                if wisclass["id"] in maskDict:
                                    for labelmask in maskDict[wisclass["id"]]:
                                        filtered = (labelmask[:, :, 0]!=0)|(labelmask[:, :, 1]!=0)|(labelmask[:, :, 2]!=0)
                                        mask[:, :, 0] = np.where(filtered, labelmask[:, :, 0], mask[:, :, 0])
                                        mask[:, :, 1] = np.where(filtered, labelmask[:, :, 1], mask[:, :, 1])
                                        mask[:, :, 2] = np.where(filtered, labelmask[:, :, 2], mask[:, :, 2])
                            if mask.max() != 0:
                                im = Image.fromarray(mask)
                                im.save(os.path.join(exportPath, mainname+'_label.png'))
            count = count + 1
            self.updateProgressBar(count / 1 * 100)


    def AutoSearchNewImageAndLabel(self, rawDataDir, callback=None):
        # 一、构建以原图名称为字典，构建原图-原图标注-新图-新图标注对应关系，补充长、宽信息
        importInfoDict = {} # {'imgName' : [importImageFile, importLabelFile, wisImageFile, wisLabelFile, width, height]]}
        importConflictInfoDict = {} # {'imgName' : [importImageFile, importLabelFile, wisImageFile, wisLabelFile, width, height]]}

        # 1.根据后缀名搜索原图列表、标注列表
        importImageList = []
        importLabelList = []
        if os.path.isfile(rawDataDir):
            importImageList.extend(glob.glob(os.path.join(os.path.dirname(rawDataDir), 'data', 'raw_data', '*')))
            importLabelList.extend(glob.glob(os.path.join(os.path.dirname(rawDataDir), 'data', 'labeled_data', '*')))
        else:
            for ext in ('*.jpg', '*.bmp', '*.jpeg', '*.png', '*.tif', '*.tiff'):
                importImageList.extend(glob.glob(os.path.join(rawDataDir, ext)))
            for ext in ('*.json', '*.txt'):
                importLabelList.extend(glob.glob(os.path.join(rawDataDir, ext)))

        # 2.根据原图列表、标注列表构建上述字典
        for img in importImageList:
            imgName, imgSuffix = os.path.splitext(os.path.basename(img))
            importImageFile = img
            wisImageFile = os.path.join(self.project.rawDataDir, imgName+imgSuffix)
            importLabelFile = None
            wisLabelFile = None
            lblFile = [lbl for lbl in importLabelList if imgName in os.path.splitext(os.path.basename(lbl))[0]]
            if len(lblFile) == 1:
                importLabelFile = lblFile[0]
                wisLabelFile = os.path.join(self.project.labeledDataDir, imgName+'.json')
            width, height = Image.open(img).size

            # 冲突检测
            lenconflict = len(glob.glob(os.path.join(self.project.rawDataDir, imgName+'.*')))
            lenconflict += len(glob.glob(os.path.join(self.project.rawDataDir, imgName+'_*[0-9].*')))
            if lenconflict:
                importConflictInfoDict[imgName] = []
                importConflictInfoDict[imgName].append(importImageFile)
                importConflictInfoDict[imgName].append(importLabelFile)
                importConflictInfoDict[imgName].append(wisImageFile)
                importConflictInfoDict[imgName].append(wisLabelFile)
                importConflictInfoDict[imgName].append(width)
                importConflictInfoDict[imgName].append(height)
            else:
                importInfoDict[imgName] = []
                importInfoDict[imgName].append(importImageFile)
                importInfoDict[imgName].append(importLabelFile)
                importInfoDict[imgName].append(wisImageFile)
                importInfoDict[imgName].append(wisLabelFile)
                importInfoDict[imgName].append(width)
                importInfoDict[imgName].append(height)

        self.total = len(importInfoDict) * 2 + 1 + 1 + 1

        # 二、构建id-类别字典(DIY无，labelme无，yolo为classes.txt，wsp工程文件classes字段)
        categoryDict = {} # {'id':type}
        yoloClasses = os.path.join(rawDataDir, 'classes.txt')
        if os.path.isfile(rawDataDir):
            with open(rawDataDir, 'r', encoding="utf-8") as file_obj:
                classesList = json.load(file_obj)['classes']
                for c in classesList:
                    categoryDict[int(c['id'])] = c['type']
        elif os.path.isfile(yoloClasses):
            with open(yoloClasses, 'r', encoding="utf-8") as file_obj:
                while True:
                    line = file_obj.readline()
                    if not line:
                        break
                    data_list = line.split()
                    categoryDict[int(data_list[0])] = data_list[-1]
        if callback:
            callback(self.total)
        # 三.根据字典进行原图/标注处理
        # method, size, mode = self.project.getResizeParam()
        labelConventor = LabelConventor(self.project.classes)
        for imgName in importInfoDict.keys():
            infoList = importInfoDict[imgName]
            labelConventor.imagelabel2wisdom(self.config.version, self.project, infoList, categoryDict, callback, self.total)

        self.project.classes = labelConventor.classes
        # 修改classification
        classification = [_class["id"] for _class in self.project.classes]
        fileList = []
        fileDict = {}
        for ext in ['*']:
            fileList.extend(glob.glob(os.path.join(self.project.labeledDataDir, ext)))
        for file in fileList:
            with open(file, 'r', encoding='utf-8') as file_obj:
                fileDict = json.load(file_obj)
                fileDict['classification'] = classification
            with open(file, 'w', encoding='utf-8') as file_obj:
                json.dump(fileDict, file_obj, indent=4, ensure_ascii=False)

        if callback:
            callback(self.total)

        # 无冲突 更新进度条
        if len(importConflictInfoDict) == 0:
            if callback:
                callback(self.total)
        # 第三步：冲突处理
        self.conflictFileNameList = list(importConflictInfoDict.keys())
        self.conflictImportResult.clear()
        if len(importConflictInfoDict) != 0:
            for conflictFile in importConflictInfoDict.keys():
                temp = {}
                temp['labelmeImageFile'] = importConflictInfoDict[conflictFile][0]
                temp['labelmeLabelFile'] = importConflictInfoDict[conflictFile][1]
                temp['categoryDict'] = categoryDict
                self.conflictImportResult.append(temp)


    def DIYRuleNewImageAndLabel(self, imageDir, labelDir, imageName, labelName,
                                imageSuffix, labelSuffix, backgroundIndex, callback=None):
        # 一、构建以原图名称为字典，构建原图-原图标注-新图-新图标注对应关系，补充长、宽信息
        importInfoDict = {} # {'imgName' : [importImageFile, importLabelFile, wisImageFile, wisLabelFile, width, height]]}
        importConflictInfoDict = {} # {'imgName' : [importImageFile, importLabelFile, wisImageFile, wisLabelFile, width, height]]}

        # 1.根据后缀名搜索原图列表、标注列表
        importImageList = []
        importLabelList = []

        # 根据规则查找图片与标注
        extImageList = []
        extImageList.extend(glob.glob(os.path.join(imageDir, imageName.replace("{}", "*") + '.' + imageSuffix)))
        extLabelList = []
        extLabelList.extend(glob.glob(os.path.join(labelDir, labelName.replace("{}", "*") + '.' + labelSuffix)))
        labelRules = re.compile(labelName.replace("{}", "(.*?)") + '.' + labelSuffix)
        lblNameList = [re.findall(labelRules, os.path.basename(lbl))[0] for lbl in extLabelList]

        if len(extImageList) == 0:
            pass
        if len(extLabelList) == 0:
            pass

        for img in extImageList:
            imgName, imgSuffix = os.path.splitext(os.path.basename(img))
            if imgName in lblNameList:
                importImageList.append(img)
                importLabelList.append(extLabelList[lblNameList.index(imgName)])
        # 2.根据原图列表、标注列表构建上述字典
        for img in importImageList:
            imgName, imgSuffix = os.path.splitext(os.path.basename(img))
            importImageFile = img
            wisImageFile = os.path.join(self.project.rawDataDir, imgName+imgSuffix)
            importLabelFile = None
            wisLabelFile = None
            lblFile = [lbl for lbl in importLabelList if imgName in os.path.splitext(os.path.basename(lbl))[0]]
            if len(lblFile) == 1:
                importLabelFile = lblFile[0]
                wisLabelFile = os.path.join(self.project.labeledDataDir, imgName+'.json')
            width, height = Image.open(img).size

            # 冲突检测
            lenconflict = len(glob.glob(os.path.join(self.project.rawDataDir, imgName+'.*')))
            lenconflict += len(glob.glob(os.path.join(self.project.rawDataDir, imgName+'_*[0-9].*')))
            if lenconflict:
                importConflictInfoDict[imgName] = []
                importConflictInfoDict[imgName].append(importImageFile)
                importConflictInfoDict[imgName].append(importLabelFile)
                importConflictInfoDict[imgName].append(wisImageFile)
                importConflictInfoDict[imgName].append(wisLabelFile)
                importConflictInfoDict[imgName].append(width)
                importConflictInfoDict[imgName].append(height)
            else:
                importInfoDict[imgName] = []
                importInfoDict[imgName].append(importImageFile)
                importInfoDict[imgName].append(importLabelFile)
                importInfoDict[imgName].append(wisImageFile)
                importInfoDict[imgName].append(wisLabelFile)
                importInfoDict[imgName].append(width)
                importInfoDict[imgName].append(height)

        self.total = len(importInfoDict) * 2 + 1 + 1

        # 二、构建id-类别字典(DIY无，labelme无，yolo为classes.txt，wsp工程文件classes字段)
        categoryDict = {} # {'id':type}

        # 三.根据字典进行原图/标注处理
        # method, size, mode = self.project.getResizeParam()
        labelConventor = LabelConventor(self.project.classes)
        for imgName in importInfoDict.keys():
            infoList = importInfoDict[imgName]
            labelConventor.imagelabel2wisdom(self.config.version, self.project, infoList, None, callback, self.total)

        self.project.classes = labelConventor.classes
        # 修改classification
        classification = [_class["id"] for _class in self.project.classes]
        fileList = []
        fileDict = {}
        for ext in ['*']:
            fileList.extend(glob.glob(os.path.join(self.project.labeledDataDir, ext)))
        for file in fileList:
            with open(file, 'r', encoding='utf-8') as file_obj:
                fileDict = json.load(file_obj)
                fileDict['classification'] = classification
            with open(file, 'w', encoding='utf-8') as file_obj:
                json.dump(fileDict, file_obj, indent=4, ensure_ascii=False)

        if callback:
            callback(self.total)
        # 无冲突 更新进度条
        if len(importConflictInfoDict) == 0:
            if callback:
                callback(self.total)
        # 第三步：冲突处理
        self.conflictFileNameList = list(importConflictInfoDict.keys())
        self.conflictImportResult.clear()
        if len(importConflictInfoDict) != 0:
            for conflictFile in importConflictInfoDict.keys():
                temp = {}
                temp['labelmeImageFile'] = importConflictInfoDict[conflictFile][0]
                temp['labelmeLabelFile'] = importConflictInfoDict[conflictFile][1]
                temp['categoryDict'] = categoryDict
                self.conflictImportResult.append(temp)

    '''
        主视图
    '''

    def updateThresholdNum(self):
        text = '{}%'.format(str(int(self.ui.horizontalSliderThreshold.value())))
        self.ui.labelThresholdNum.setText(text)

    def setResThreshold(self):
        if self.ui.comboBoxSliderThreshold.currentText() == '分割结果':
            thres = self.ui.horizontalSliderThreshold.value() / 100
            self.MainGraphicsView.changeLabelThres(thres, 'Scraw')
        elif self.ui.comboBoxSliderThreshold.currentText() == '检测结果':
            thres = self.ui.horizontalSliderThreshold.value() / 100
            self.MainGraphicsView.changeLabelThres(thres, 'Rectangle')
        self.updateThresholdNum()

    def switchWidgetThreshold(self):
        self.ui.comboBoxSliderThreshold.clear()
        count = 0
        for _class in self.project.classes:
            type = _class['type']
            scrawLabel = self.MainGraphicsView.getLabel(type, 'Scraw')
            rectLabels = self.MainGraphicsView.getAllLabels(type, 'Rectangle')
            if scrawLabel is not None and not math.isnan(scrawLabel.confidence) and scrawLabel.confidence != 1:
                self.ui.comboBoxSliderThreshold.addItem('分割结果')
                self.ui.horizontalSliderThreshold.setValue(50)
                self.setResThreshold()
                count += 1
            if len(rectLabels) != 0:
                for rectLabel in rectLabels:
                    if not math.isnan(rectLabel.confidence) and rectLabel.confidence != 1:
                        self.ui.comboBoxSliderThreshold.addItem('检测结果')
                        self.ui.horizontalSliderThreshold.setValue(0)
                        self.setResThreshold()
                        count += 1
                        break
        if count < 1:
            self.ui.widgetThreshold.setVisible(False)
        else:
            self.ui.widgetThreshold.setVisible(True)

    def thresholdEnsure(self):
        self.ui.widgetThreshold.setVisible(False)
        for _class in self.project.classes:
            type = _class["type"]
            scrawLabel = self.MainGraphicsView.getLabel(type, 'Scraw')
            if self.ui.comboBoxSliderThreshold.currentText() == '分割结果' and scrawLabel is not None:
                scrawLabel.confThresEnsure()
            rectLabels = self.MainGraphicsView.getAllLabels(type, 'Rectangle')
            if self.ui.comboBoxSliderThreshold.currentText() == '检测结果' and len(rectLabels) != 0:
                for label in rectLabels:
                    label.confThresEnsure()
        # 新增标注数量
        for label in self.MainGraphicsView.labelList:
            if label.Die == False:
                for _class in self.project.classes:
                    if label.type == _class["type"]:
                        if label.labelClass == "Scraw":
                            _class["scraw"] += 1
                        elif label.labelClass == "Rectangle" or label.labelClass == "PolygonCurve" or label.labelClass == "Point" or label.labelClass == "Tag" or label.labelClass == "Line" or label.labelClass == "Circle":
                            _class["instance"] += 1
        self.save(self.fileList[self.ui.listwidgetFile.currentRow() + self.pageSize * (self.currentPage - 1)].get('path'))
        self.setCurLabelStatus()
        self.setTargetSideBar()
        self.setTypeSideBar()
        # 推理已确认后标注可转换
        self.ui.tBtnToPolygonLabel.setEnabled(True)
        self.ui.tBtnToScrawLabel.setEnabled(True)
        self.ui.tBtnFill.setEnabled(True)

    '''
        标注视图右键菜单
    '''

    def createRightMenuMain(self):
        self.menuShowingMain = False

        self.menuMain = QMenu(self)
        self.menuMain.setStyleSheet(Style_QMenu)
        # 删除
        self.actionDeleteMain = QAction(u'删除', self)  # 创建菜单选项对象
        self.menuMain.addAction(self.actionDeleteMain)
        self.actionDeleteMain.triggered.connect(lambda: self.MainGraphicsView.deleteSelectedLabel(None))
        # 更改类别
        self.classSelection = QMenu(u'更换类别', self)
        self.classSelectionMain = []
        # classes = copy.deepcopy(self.project.classes)
        # for cls_ in classes:
        #     action = self.openPadActionMain(cls_)
        #     action.setCheckable(True)
        #     self.classSelectionMain.append(action)
        #     self.classSelection.addAction(action)
        # self.menuMain.addMenu(self.classSelection)
        # 删除点
        self.actionDeletePointMain = QAction(u'删除该点', self)  # 创建菜单选项对象
        self.menuMain.addAction(self.actionDeletePointMain)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.menuMainShowMain)  # 连接到菜单显示函数

    def openPadActionMain(self, newCls):
        action = QAction(newCls['type'], self)
        action.triggered.connect(lambda: self.MainGraphicsView.changeLabelClass(newCls))
        return action

    def menuMainShowMain(self, pos):
        #屏蔽grabcut的右键菜单
        if self.ui.tBtnRectmode.isChecked():
            return
        selectedLabel = self.MainGraphicsView.labelSelected()
        if selectedLabel:
            if isinstance(selectedLabel, PolygonCurveLabel):
                if selectedLabel.addCtl or selectedLabel.modifing:
                    return
            self.menuShowing = True
            # 菜单类别
            classes = copy.deepcopy(self.project.classes)
            self.classSelection.clear()
            self.classSelectionMain.clear()
            for cls_ in classes:
                if cls_['id'] == 0:
                    continue
                action = self.openPadActionMain(cls_)
                action.setCheckable(True)
                self.classSelectionMain.append(action)
                self.classSelection.addAction(action)
            self.classSelection.setStyleSheet(Style_QMenu)
            self.menuMain.addMenu(self.classSelection)
            for action in self.classSelectionMain:
                if selectedLabel.type == action.text():
                    action.setChecked(True)
                else:
                    action.setChecked(False)
            # 菜单关键点
            mPos = QCursor.pos()
            mlocPos = self.MainGraphicsView.mapToScene(self.MainGraphicsView.mapFromGlobal(mPos))

            if isinstance(selectedLabel, PolygonCurveLabel):
                if selectedLabel.selectedPointIndex(mlocPos.x(), mlocPos.y()) != -1 and selectedLabel.polygon.count() > 3:
                    self.actionDeletePointMain.setEnabled(True)
                    self.actionDeletePointMain.setVisible(True)
                else:
                    self.actionDeletePointMain.setEnabled(False)
                    self.actionDeletePointMain.setVisible(False)
            else:
                self.actionDeletePointMain.setEnabled(False)
                self.actionDeletePointMain.setVisible(False)

            action = self.menuMain.exec(mPos)
            if action == self.actionDeletePointMain:
                self.MainGraphicsView.deleteKeyPoint(mlocPos)

    '''
        label标注列表右键菜单
    '''

    def createRightMenuLabelTable(self):

        self.menuLabelTable = QMenu(self)
        self.menuLabelTable.setStyleSheet(Style_QMenu)
        # 删除
        self.actionDeleteLabelTable = QAction(u'删除', self)  # 创建菜单选项对象
        self.menuLabelTable.addAction(self.actionDeleteLabelTable)
        # 更改类别
        self.classSelection = QMenu(u'更换类别', self)
        self.classSelection.setStyleSheet(Style_QMenu)
        self.classSelectionLabelTable = []
        # classes = copy.deepcopy(self.project.classes)
        # for cls_ in classes:
        #     action = QAction(cls_['type'], self)
        #     action.setCheckable(True)
        #     self.classSelection.addAction(action)
        #     self.classSelectionLabelTable.append(action)
        # self.menuLabelTable.addMenu(self.classSelection)
        self.ui.tableWidgetTargetList.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ui.tableWidgetTargetList.customContextMenuRequested.connect(self.menuLabelTableShow)  # 连接到菜单显示函数

    def menuLabelTableShow(self, pos):
        indexes = self.ui.tableWidgetTargetList.selectionModel().selection().indexes()
        self.classSelection.clear()
        self.classSelectionLabelTable.clear()
        classes = copy.deepcopy(self.project.classes)
        for cls_ in classes:
            if cls_['id'] == 0:
                continue
            action = QAction(cls_['type'], self)
            action.setCheckable(True)
            self.classSelection.addAction(action)
            self.classSelectionLabelTable.append(action)
        self.menuLabelTable.addMenu(self.classSelection)
        rowIndexSet = set()
        for index in indexes:
            rowIndex = index.row()
            rowIndexSet.add(rowIndex)
            # selectedLabel = self.MainGraphicsView.labelList[rowIndex]
            # for action in self.classSelectionLabelTable:
            #     if selectedLabel.type == action.text():
            #         action.setChecked(True)
            #     else:
            #         action.setChecked(False)
        rowIndexList = list(rowIndexSet)
        rowIndexList.sort(reverse=True)
        screenPos = self.ui.tableWidgetTargetList.mapToGlobal(pos)
        action = self.menuLabelTable.exec(screenPos)
        saveScrawFlag = False
        if self.ui.tBtnBrush.isChecked():
            saveScrawFlag = True
        if action == self.actionDeleteLabelTable:
            for rowIndex in rowIndexList:
                self.MainGraphicsView.deleteSelectedLabel(rowIndex, saveScrawFlag)
        elif action in self.classSelectionLabelTable:
            clsName = action.text()
            for cls_ in self.project.classes:
                if cls_['type'] == clsName:
                    for rowIndex in rowIndexList:
                        self.MainGraphicsView.changeLabelClass(cls_, rowIndex)

    def clearUndoStack(self):
        self.MainGraphicsView.undoStack.clear()
        self.MainGraphicsView.undoAction.setEnabled(False)
        self.MainGraphicsView.redoAction.setEnabled(False)

    def wheelEvent(self,event: QtGui.QWheelEvent) -> None:
        if self.MainGraphicsView.allowIntelligentScissors:
            self.ui.ScissorsAreaSlider.setValue(self.MainGraphicsView.square_size)

if __name__ == '__main__':
    # 自适应高分辨率屏幕（注意放在QApplication创建之前）
    QtCore.QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling)  # 适应windows缩放
    QtGui.QGuiApplication.setAttribute(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)  # 设置支持小数放大比例（适应如125%的缩放比）
    app = QApplication(sys.argv)
    auth = Auth()
    config = Config()
    myProject = Project()
    # myProject.load(r'C:\Users\A\wisdom_store_workspace\Project1\project.json')
    # myProject.load(r'C:\Users\yofer\wisdom_store_workspace\Local\Test\project.json')
    myProject.load(r'C:\Users\yofer\wisdom_store_workspace\Local\YoloDetection\project.json')
    myWin = MainWin(config, auth, myProject)
    myWin.show()
    # metrix = np.load(r"C:\Users\A\Desktop\label_data_array.npy")
    # myWin.saveNumpyToJsonLabelFile("XXX",metrix,["前景"],"XXX",[1.0])
    sys.exit(app.exec_())
