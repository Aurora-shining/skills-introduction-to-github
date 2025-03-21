from http.client import INSUFFICIENT_STORAGE

from PyQt5.QtWidgets import QGraphicsView, QGraphicsPixmapItem, QGraphicsScene, QUndoCommand, QUndoStack, QPushButton, QGraphicsRectItem, QGraphicsTextItem
from PyQt5 import QtGui, QtWidgets, QtCore
from PyQt5.QtGui import QImage, QPixmap, QColor, QPolygonF, QCursor, QKeySequence, QIcon, QPen, QBrush, QFont, QPainter
from PyQt5.QtCore import Qt, pyqtSignal, QMutex, QWaitCondition
from PyQt5.QtCore import QRectF, QSizeF, QPoint, QPointF, QRect, QRectF
from wisdom_store.src.utils.image_transform import imgPixmapToNmp, nmpToImgPixmap

from wisdom_store.ui.main.UI_Label import RectCut, RectLabel, LineLabel, ScrawLabel, MouseHoverScrawLabel, ScrawCursor, \
    PointLabel, TagLabel, \
    CircleLabel, PolygonCurveLabel, Rect_mask_Label, Feedback_PointLabel, RulerLabel, IntelligentScissors
from wisdom_store.ui.main.UI_MyGraphicsView import MyGraphicsView
from wisdom_store.video_annotation.MagnifyingGlass import MagnifyingGlass
from wisdom_store.src.utils.grabcut import grabcut_fun
from wisdom_store.config import Config

from PIL import ImageQt, Image
import numpy as np

import os
from enum import Enum
import cv2
import matplotlib.pyplot as plt
from scipy.integrate import quad

# RITM
import torch
from wisdom_store.src.utils.RITM.isegm.inference import clicker
from wisdom_store.src.utils.RITM.isegm.inference.predictors import get_predictor
from wisdom_store.src.utils.RITM.isegm.inference import utils
from wisdom_store.wins.WidgetWinCustom import CommonThread
from wisdom_store.wins.component_waiting import WaitingWin

from wisdom_store.wins.component_alert_message import alertError
from wisdom_store.src.sdk.project.project import Project
# efficientvitSAM
from wisdom_store.src.utils.efficientvitsam import efficientvit_build_model
from wisdom_store.src.utils.efficientvitsam import EfficientvitSAM

# efficientSAM
import onnxruntime
import time
# 计算时间
from PyQt5.QtCore import QTimer


class paintTool():
    Rect = 0
    Polygon = 1
    Line = 2
    Scraw = 3


class zoomMode():
    NoZoom = 0
    ZoomIn = 1
    ZoomOut = 2


class STATUSMode(Enum):
    # SAM
    VIEW = 0
    CREATE = 1
    EDIT = 2

# 用于近邻标注
class PointWithFlag:
    def __init__(self, point, flag):
        self.point = point
        self.flag = flag

class MainGraphicsView(MyGraphicsView):
    needSaveItem = pyqtSignal(bool)
    labelSelect = pyqtSignal(str)
    sizeChanged = pyqtSignal(QRectF)
    scaleChanged = pyqtSignal(float)
    labelNumChanged = pyqtSignal()
    paintUsed = pyqtSignal()
    pixelString = pyqtSignal(str)
    changeScrawPenSize = pyqtSignal(bool)
    changeThresholdValue = pyqtSignal(bool)
    labelCreateFinished = pyqtSignal(bool)
    singleAddLabelNum = pyqtSignal(str, str)
    singleSubLabelNum = pyqtSignal(str, str)
    rulerCreatingSuccess = pyqtSignal(float)

    def __init__(self, parent, config: Config, project: Project, mainWin):
        super(MainGraphicsView, self).__init__(parent=parent)
        self.project = project
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.horizontalScrollBar().valueChanged.connect(self.updateBirdView)
        self.verticalScrollBar().valueChanged.connect(self.updateBirdView)
        self.config = config
        self.mainWin = mainWin
        self.ZoomMode = False
        self.horiWheel = False
        self.vertiWheel = False
        self.click_shift_mode = False

        self.rulerLabel = None

        self.handTool = True
        self.allowRect = False
        self.allowPolygon = False
        self.allowLine = False
        self.allowScraw = False
        self.allowPoint = False
        self.allowTag = False
        self.allowCircle = False
        self.updatePixel = True
        self.allowGrabCut = False
        self.allowAiScraw = False
        self.allowAIMagic = False
        self.allowInteract = False
        self.allowText = False
        self.allowMove = False
        self.allowRectCut = False
        self.rectItem = None
        self.allowRecons = False
        self.allowRuler = False
        self.allowIntelligentScissors = False
        self.inferCompleted = False
        #A修改
        self.showCenters = False

        self.zoomMode = zoomMode.NoZoom
        self.birdViewShow = True
        self.magnifying = False
        self.magnifyingGlass = None

        self.grabCutStp = None
        self.grabCutEdp = None

        self.is_bgcolor = False  # 当前类别是否为背景类，如果是，则涂鸦左键具有擦除功能。
        self.erase_points = []

        self.current_type = "XXX"
        self.current_color = QColor(255, 0, 0)
        self.operator = "XXX"
        self.setFocus()

        self.alpha = 127
        self.alphaSelect = 191

        # 开启追踪
        self.setMouseTracking(True)

        # 用于连续标注
        self.mutex = QMutex()
        self.cond = QWaitCondition()

        self.magnifyingGlass = None
        self.scrawCursor = None
        self.rightClicked = False

        # 软件状态初始化
        self.labelInteract = False
        self.setLabelsInteract(False)

        # self.setViewportUpdateMode(QGraphicsView.BoundingRectViewportUpdate)

        self.undoStack = QUndoStack()
        self.undoStack_feedback = QUndoStack()

        # init action
        self.undoAction = self.undoStack.createUndoAction(self, "撤销 (Ctrl+Z)")
        self.undoAction.setShortcut(QKeySequence.Undo)
        self.undoAction.setShortcutVisibleInContextMenu(False)
        self.undoAction.setIcon(QIcon(":/resources/撤销.png"))
        self.undoAction.triggered.connect(lambda: self.EfficientvitSAM_undo())

        self.redoAction = self.undoStack.createRedoAction(self, "重做 (Ctrl+Y)")
        self.redoAction.setShortcut(QKeySequence.Redo)
        self.redoAction.setShortcutVisibleInContextMenu(False)
        self.redoAction.setIcon(QIcon(":/resources/重做.png"))
        self.redoAction.triggered.connect(lambda: self.EfficientvitSAM_redo())

        self.addAction(self.undoAction)
        self.addAction(self.redoAction)
        self.grabcut_iter_count = 1
        self.grabcut_flag = None
        self.grabcut_width = 0
        self.grabcut_height = 0
        self.grabcutx = 0
        self.grabcuty = 0
        self.grabcut_run = None
        # grabcut连续标注flag

        self.labelGPUResource = QtWidgets.QLabel('')
        self.labelGPUResource.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        self.labelGPUResource.setFixedWidth(180)
        # 目前只提供一种方法 efficientvitsam 下拉框功能暂时禁用
        self.ai_model = "efficientvitsam"
        self.is_positive = None
        self.probs_history = []
        self._init_mask = None
        self.ritm_states = []
        self.clicker = clicker.Clicker()
        self.predictor = None
        self.net = None
        self.device = None
        self.RITM_result_mask = None
        self.image_RITM = None
        # RITM
        self.box_prompt = []
        # AIMagic
        self.rect_mask_temp_dict = {}
        # Efficent_ONNX
        self.image_EfficientvitSAM = None
        self.efficientvitSAM_x = 0
        self.efficientvitSAM_y = 0
        self.Clickmode = True
        self.Hovermode = False
        self.erasermode = False
        # 用于判定切出智能标注时，是否是刷子状态
        self.brushflag = False
        # EfficientvitSAM_instance
        self.EfficientvitSAM_predictor = None
        self.EfficientvitSAM_instance = None
        self.efficientvitSAM_enable = False

        # 创建确认和取消按钮，并设置样式
        self.confirmButton = QPushButton(self)
        self.confirmButton.setIcon(QIcon(r".\wisdom_store\ui\main\resources\confirm_button.png"))
        self.confirmButton.clicked.connect(self.confirmCrop)
        self.confirmButton.hide()
        self.confirmButton.setStyleSheet("background-color: transparent; border: none;")
        icon_size = self.confirmButton.iconSize()
        self.confirmButton.setIconSize(icon_size * 2.5)

        self.cancelButton = QPushButton(self)
        self.cancelButton.setIcon(QIcon(r".\wisdom_store\ui\main\resources\cancel_button.png"))
        self.cancelButton.clicked.connect(self.cancelCrop)
        self.cancelButton.hide()
        self.cancelButton.setStyleSheet("background-color: transparent; border: none;")
        icon_size = self.cancelButton.iconSize()
        self.cancelButton.setIconSize(icon_size * 2.5)

        # 用于近邻标注
        self.quick = False
        self.selectedlabel=None
        self.creatinglabel = None
        self.point1=None
        self.p1num = -2
        self.s1=-2
        self.p1num_crealabel=-1
        self.cre_num_bef_quick = None
        self.polygon_quick_clicknum = -1
        self.temp_ptnum = None

        # 用于智慧剪刀
        self.count = 0#一个用于帮助智慧剪刀实时刷新的工具变量
        self.g4 = QPointF()#鼠标左键点击后保留的搜索框的左上角坐标
        self.g3 = QPointF()#鼠标左键点击后保留的搜索框的右下角坐标
        self.g2 = None#淡蓝框的左上角坐标
        self.g1 = None#淡蓝色框的右下角坐标
        self.square_size = 200#框的边长
        self.square_pos = None#框的上下左右的坐标，g1 g2 作用一样
        self.contours = None#智慧剪刀，从确定点到鼠标所在点的路径
        self.tool = None#cv2.segmentation_IntelligentScissorsMB()
        self.hasMap = None#检验所点击点是否在画布里的变量
        self.src = None#裁剪过的图片，np格式
        self.creatinglabel = None
        self.scissors = None#是否开始启动智慧剪刀
        self.image = None#当前的图片，np格式
        self.ScissorspPointNum=4#点的初始密度

    def initState(self):
        '''
        初始化控件状态
        '''
        self.handTool = False
        self.allowRect = False
        self.allowPolygon = False
        self.allowLine = False
        self.allowPoint = False
        self.allowTag = False
        self.allowCircle = False
        self.allowScraw = False
        self.allowRuler = False
        self.allowAiScraw = False
        self.magnifying = False
        self.allowAIMagic = False
        self.birdViewShow = False
        self.changeScrawMode(False)
        self.changeMagnify(False)
        self.setLabelsInteract(False)
        # self.setLabelsAllowMove(False)
        self.setDragMode(QGraphicsView.NoDrag)
        self.unsetCursor()
        self.changeZoomMode(zoomMode.NoZoom)
        # self.mutex.unlock()
        self.grabcut_flag = False
        # grabcut连续标注
        # RITM
        self.is_positive = True
        self.probs_history = []
        self.RITM_result_mask = None
        self._init_mask = None
        self.ritm_states = []
        self.clicker = clicker.Clicker()
        self.box_prompt = []
        self.allowRectCut = False
        self.efficientvitSAM_enable = False
        # 智慧剪刀
        self.allowIntelligentScissors=False

    # def save_temp_mask_data(self,key):
    #     self.rect_mask_temp_dict[key] = [self.probs_history,self.RITM_result_mask,self.ritm_states,self.clicker]
    def save_temp_mask_data(self, key, label_type):
        rect_mask_temp_dict_type = {}
        rect_mask_temp_dict_type[label_type] = [self.probs_history, self.RITM_result_mask, self.ritm_states,
                                                self.clicker]
        # self.rect_mask_temp_dict = {key:self.rect_mask_temp_dict_type}
        self.rect_mask_temp_dict[key] = rect_mask_temp_dict_type
        self.probs_history = []
        self.RITM_result_mask = None
        self.ritm_states = []
        self.clicker = clicker.Clicker()
        # self.rect_mask_temp_dict = {key:self.rect_mask_temp_dict_type}
        print('nul')

    def load_temp_mask_data(self, key, label_type):
        if key in self.rect_mask_temp_dict:
            for k1, v1 in self.rect_mask_temp_dict.items():
                if k1 == key:
                    for k2, v2 in v1.items():
                        if k2 == label_type:
                            self.probs_history = self.rect_mask_temp_dict[key][label_type][0]
                            self.RITM_result_mask = self.rect_mask_temp_dict[key][label_type][1]
                            self.ritm_states = self.rect_mask_temp_dict[key][label_type][2]
                            self.clicker = self.rect_mask_temp_dict[key][label_type][3]
                        else:
                            print("no data for this type")
                else:
                    print("no data for this picture")
        print("load temp data success")

    def openNewImage(self, path):
        '''
        打开新图像
        '''
        self.myScene.clear()
        self.loadImg(path)
        self.labelList = []
        self.setViewCenter(QPoint(self.microImg.width() / 2, self.microImg.height() / 2))
        self.setScale(1.0)
        self.updateBirdView()

        self.magnifyingGlass = MagnifyingGlass(self)
        self.myScene.addItem(self.magnifyingGlass)
        self.magnifyingGlass.setVisible(False)
        self.magnifyingGlass.microImg = self.microImg

        self.scrawCursor = ScrawCursor(self.microImg.width(), self.microImg.height(), self._scale)
        self.myScene.addItem(self.scrawCursor)
        self.scrawCursor.setVisible(False)

    def updateBirdView(self):
        '''
        更新鸟瞰图
        '''
        if not self.birdViewShow:
            return
        w, h = self.microImg.width(), self.microImg.height()
        topLeft = self.mapToScene(self.viewport().rect().topLeft())
        bottomRight = self.mapToScene(self.viewport().rect().bottomRight())
        self.sizeChanged.emit(QRectF(topLeft, bottomRight))

    def setViewCenter(self, pos):
        '''
        设置视图中心
        '''
        newPos = pos * self._scale
        self.centerOn(newPos)
        self.setFocus()

    def getScaledImgRectF(self):
        '''
        生成图像相同大小的QRECT
        '''
        width = self.microImg.width() * self._scale
        height = self.microImg.height() * self._scale
        return QRectF(self.microImg.rect().topLeft(), QSizeF(width, height))

    def adjustSceneRect(self):
        '''
        调整graphicsview的sceneRect
        '''
        width = self.microImg.width() * self._scale
        height = self.microImg.height() * self._scale
        # self.myScene.setSceneRect(0, 0, width, height)
        self.setSceneRect(0, 0, width, height)
        # self.setSceneRect(self.mapToScene(self.rect()).boundingRect())
        for label in self.labelList:
            # label.update()
            if label.Die != True:
                label.pRect = self.mapToScene(self.rect()).boundingRect()
                # label.cRect = self.microImgRectF()
                # self.myScene.removeItem(label)
                # self.myScene.addItem(label)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        '''
        鼠标点击事件，标注的入口
        '''
        # super(MainGraphicsView, self).mousePressEvent(event)
        # print('view pressed')
        s = event.localPos()
        g = self.mapToScene(s.x(), s.y()) / self._scale
        flag = False
        its = self.items(s.toPoint())
        for it in its:
            if it is not None and it.isSelected():
                flag = True

        self.updateBirdView()
        if event.buttons() & Qt.RightButton:
            self.rightClicked = True
        else:
            self.rightClicked = False

        # 近邻标注
        if self.rightClicked == False and self.allowPolygon:
            if self.quick and self.polygon_quick_clicknum == 1:
                self.quick = False
                self.point1 = None
                self.selectedlabel.hoverPointIndex = -1
                self.selectedlabel.quicked = False
                self.selectedlabel = None
                self.p1num = -1
                self.p1num_crealabel = -1
                self.polygon_quick_clicknum = -1
                self.cre_num_bef_quick = -1
                self.temp_ptnum = None
            if self.quick and self.polygon_quick_clicknum == 0:
                flag = False
                for i in range(len(self.selectedlabel.polygon)):
                    t_point = self.selectedlabel.polygon.value(i)
                    t_dist = (g.x() - t_point.x()) ** 2 + (g.y() - t_point.y()) ** 2
                    if t_dist <= (self.selectedlabel.h_diameter / 2) ** 2:
                        self.polygon_quick_clicknum = 1
                        self.point1 = self.selectedlabel.polygon.value(i)
                        self.p1num = self.selectedlabel.CheckPointNum(self.point1)
                        self.selectedlabel.points_with_flags[self.p1num].flag = True
                        self.s1 = self.p1num
                        self.creatinglabel = self.WhichCreating()
                        if type(self.creatinglabel) == PolygonCurveLabel:
                            self.creatinglabel.prepareGeometryChange()
                            while len(self.creatinglabel.polygon) > self.creatinglabel.pointNum:
                                self.creatinglabel.polygon.remove(len(self.creatinglabel.polygon) - 1)
                                self.creatinglabel.prectl.remove(len(self.creatinglabel.prectl) - 1)
                                self.creatinglabel.nexctl.remove(len(self.creatinglabel.nexctl) - 1)
                            newPoint = self.point1
                            newPointprectl = self.selectedlabel.prectl.value(self.s1)
                            newPointnexctl = self.selectedlabel.nexctl.value(self.s1)
                            self.creatinglabel.polygon.append(newPoint)
                            self.creatinglabel.prectl.append(newPointprectl)
                            self.creatinglabel.nexctl.append(newPointnexctl)
                            self.creatinglabel.pointNum = self.creatinglabel.pointNum + 1
                            self.p1num_crealabel = self.creatinglabel.pointNum - 1
                            self.cre_num_bef_quick = self.creatinglabel.pointNum
                            #self.creatinglabel.cre_num_bef_quick=self.cre_num_bef_quick
                            flag=True
                            self.creatinglabel.update()
                            self.update()
                        self.selectedlabel.update()
                        self.update()
                        break
                # 下面为未选择点1后 不在点内的情况就退出
                if flag == False:
                    self.quick = False
                    self.point1 = None
                    self.selectedlabel.hoverPointIndex = -1
                    self.selectedlabel.quicked = False
                    self.selectedlabel = None
                    self.p1num = -1
                    self.p1num_crealabel = -1
                    self.polygon_quick_clicknum = -1
                    self.cre_num_bef_quick = -1
                    self.temp_ptnum = None
        #选中多边形
        if self.rightClicked == True and self.allowPolygon and self.polygon_quick_clicknum==-1:
            if self.quick == False and len(self.labelList) != 0:
                for label in self.labelList:
                    if type(label) == PolygonCurveLabel:
                        if label.creating == False and label.Die == False:
                            is_inside = label.polygon.containsPoint(g, Qt.OddEvenFill)
                            if is_inside:
                                self.quick = True
                                self.selectedlabel = label
                                self.selectedlabel.quicked = True
                                self.polygon_quick_clicknum = 0
                                self.selectedlabel.focusedPointIndex=-1
                                self.selectedlabel.points_with_flags = [PointWithFlag(point, False) for point in
                                                                        self.selectedlabel.polygon]
                                creatinglabel = self.WhichCreating()
                                if creatinglabel:
                                    creatinglabel.quicked = True
                                break
                            else:
                                pass
            else:
                pass

        if self.rightClicked == False and flag == False:
            if self.allowRect == True and self.mutex.tryLock():
                t_label = self.loadLabel(
                    RectLabel(
                        QRectF(self.pointNormalized(self.mapToScene(event.pos()) / self._scale), QSizeF(0, 0)),
                        self.mapToScene(self.rect()).boundingRect(),
                        self.microImgRectF(),
                        QColor(255, 255, 255),
                        self.current_color,
                        self.current_type,
                        self.operator,
                        1.0000
                    )
                )
                self.pushAddStack(t_label)

            elif self.allowPolygon == True and self.mutex.tryLock():
                t_label = self.loadLabel(
                    PolygonCurveLabel(
                        QPolygonF([self.pointNormalized(self.mapToScene(event.pos()) / self._scale)]),
                        None,
                        None,
                        self.mapToScene(self.rect()).boundingRect(),
                        self.microImgRectF(),
                        QColor(255, 255, 255),
                        self.current_color,
                        self.current_type,
                        self.operator,
                        1.0000
                    )
                )
                self.pushAddStack(t_label)

            elif self.allowLine == True and self.mutex.tryLock():
                t_label = self.loadLabel(
                    LineLabel(
                        QPolygonF([self.pointNormalized(self.mapToScene(event.pos()) / self._scale)]),
                        self.mapToScene(self.rect()).boundingRect(),
                        self.microImgRectF(),
                        QColor(255, 255, 255),
                        self.current_color,
                        self.current_type,
                        self.operator,
                        1.0000
                    )
                )
                self.pushAddStack(t_label)

            elif self.allowPoint == True and self.mutex.tryLock():
                t_label = self.loadLabel(
                    PointLabel(
                        self.pointNormalized(self.mapToScene(event.pos()) / self._scale),
                        self.mapToScene(self.rect()).boundingRect(),
                        self.microImgRectF(),
                        QColor(255, 255, 255),
                        self.current_color,
                        self.current_type,
                        self.operator,
                        1.0000
                    )
                )
                self.pushAddStack(t_label)

            elif self.allowTag == True and self.mutex.tryLock():
                for label in self.labelList:  # 每张图像只能有一个Tag
                    if label.labelClass == 'Tag':
                        label.Die = True
                self.singleAddLabelNum.emit(self.current_type, "Tag")
                t_label = self.loadLabel(
                    TagLabel(
                        QPoint(0, 0),
                        self.mapToScene(self.rect()).boundingRect(),
                        self.microImgRectF(),
                        QColor(255, 255, 255),
                        self.current_color,
                        self.current_type,
                        self.operator,
                        1.0000
                    )
                )
                self.pushAddStack(t_label)

            elif self.allowCircle == True and self.mutex.tryLock():
                t_label = self.loadLabel(
                    CircleLabel(
                        (self.pointNormalized(self.mapToScene(event.pos()) / self._scale), 0, 0),
                        self.mapToScene(self.rect()).boundingRect(),
                        self.microImgRectF(),
                        QColor(255, 255, 255),
                        self.current_color,
                        self.current_type,
                        self.operator,
                        1.0000
                    )
                )
                self.pushAddStack(t_label)

            elif self.allowRectCut == True and self.mutex.tryLock():
                # 创建矩形框
                self.rectCut = self.loadLabel(
                    RectCut(
                        QRectF(self.pointNormalized(self.mapToScene(event.pos()) / self._scale), QSizeF(0, 0)),
                        self.mapToScene(self.rect()).boundingRect(),
                        self.microImgRectF(),
                        QColor(255, 255, 255),
                        QColor(255, 255, 255),
                        self.current_type,
                        self.operator,
                        1.0000
                    )
                )
                self.rectCutText = QGraphicsTextItem()
                self.myScene.addItem(self.rectCutText)
                self.rectCutText.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
                self.rectCutText.setDefaultTextColor(QColor(255, 255, 255))

            elif self.allowIntelligentScissors == True and self.mutex.tryLock():
                t_label = self.loadLabel(
                    IntelligentScissors(
                        QPolygonF([self.pointNormalized(self.mapToScene(event.pos()) / self._scale)]),
                        None,
                        None,
                        self.mapToScene(self.rect()).boundingRect(),
                        self.microImgRectF(),
                        QColor(255, 255, 255),
                        self.current_color,
                        self.current_type,
                        self.operator,
                        1.0000
                    )
                )
                self.pushAddStack(t_label)

        if self.rightClicked == False and self.allowIntelligentScissors:
            self.creatinglabel = self.WhichCreating()
            self.image = np.array(ImageQt.fromqpixmap(self.microImg))
            self.g3 = self.g1
            self.g4 = self.g2
            if self.g1.x() < 0:
                self.g3=QPointF(0,self.g3.y())
            if self.g1.y() < 0:
                self.g3=QPointF(self.g3.x(),0)
            if self.g2.x() > self.image.shape[1]:
                self.g4=QPointF(self.image.shape[1],self.g4.y())
            if self.g2.y() > self.image.shape[0]:
                self.g4=QPointF(self.g4.x(),self.image.shape[0])
            self.src=self.image[int(self.g3.y()):int(self.g4.y()),int(self.g3.x()):int(self.g4.x())]
            #plt.imshow(self.src)
            #plt.show()
            self.scissors = True
            start = time.time()
            self.tool = cv2.segmentation_IntelligentScissorsMB()
            self.tool.setEdgeFeatureCannyParameters(32, 100)  # 设置 Canny 边缘检测参数
            self.tool.setGradientMagnitudeMaxLimit(200)  # 设置梯度幅度最大限制
            self.tool.applyImage(self.src)  # 应用图像
            self.hasMap = False
            end = time.time()
            #print('1.Running time: %s Seconds' % (end - start))
            if 0 < g.x() - self.g3.x() < self.src.shape[1] and 0 < g.y() - self.g3.y() < self.src.shape[0] and self.creatinglabel != None:  # 检查点击是否在图像范围内
                #print('Building map...')
                start = time.time()
                #print("square_size")
                #print(self.square_size)
                self.tool.buildMap((int(g.x()-self.g3.x()), int(g.y()-self.g3.y())))  # 建立地图
                end = time.time()
                #print('2.Running time: %s Seconds' % (end - start))
                #print('Map built.')
                self.hasMap = True
                self.count=len(self.creatinglabel.polygon)
                # self.rectItem = QGraphicsRectItem(scene_pos.x(), scene_pos.y(), 0, 0)
                # # 设置画笔为白色
                # pen = QPen(Qt.white, 2, Qt.SolidLine)  # 白色、线条宽度为1、实线样式

                # # 设置填充样式为透明
                # brush = QBrush(QColor(128, 128, 128, 128))  # 半透明填充

                # self.rectItem.setPen(pen)
                # self.rectItem.setBrush(brush)
                # self.scene().addItem(self.rectItem)

                # # 记录矩形框起始位置
                # self.rectStartPos = scene_pos
                # # 连接鼠标移动事件
                # self.mouseMoveEvent = self.handleMouseMove
                # # 连接鼠标释放事件
                # self.mouseReleaseEvent = self.getFinalPos
        # if self.allowGrabCut and self.is_bgcolor == False and self.rightClicked == False and self.mutex.tryLock():
        #     t_label = self.grabcut_loadLabel(
        #         Rect_mask_Label(
        #             QRectF(self.pointNormalized(self.mapToScene(event.pos()) / self._scale), QSizeF(0, 0)),
        #             self.mapToScene(self.rect()).boundingRect(),
        #             self.microImgRectF(),
        #             QColor(255, 255, 255),
        #             self.current_color,
        #             self.current_type,
        #             self.operator,
        #             1.0000
        #         )
        #     )
        # elif self.allowGrabCut and self.ai_model == "经典方法" and self.is_bgcolor == False and self.rightClicked == True and self.mutex.tryLock():
        #     t_label = self.grabcut_loadLabel(
        #         Rect_mask_Label(
        #             QRectF(self.pointNormalized(self.mapToScene(event.pos()) / self._scale), QSizeF(0, 0)),
        #             self.mapToScene(self.rect()).boundingRect(),
        #             self.microImgRectF(),
        #             QColor(255, 255, 255),
        #             QColor(255, 255, 255),
        #             self.current_type,
        #             self.operator,
        #             1.0000
        #         )
        #     )

        # 20240730新增，EfficientvitSAM画框标注
        if self.allowAIMagic and self.allowGrabCut and self.is_bgcolor == False and self.mutex.tryLock():
            # 进入画框标注且不是背景类且未锁
            if self.rightClicked == False and self.click_shift_mode == False:
                # 左键且不按shift
                t_label = self.grabcut_loadLabel(
                    Rect_mask_Label(
                        QRectF(self.pointNormalized(self.mapToScene(event.pos()) / self._scale), QSizeF(0, 0)),
                        self.mapToScene(self.rect()).boundingRect(),
                        self.microImgRectF(),
                        QColor(255, 255, 255),
                        self.current_color,
                        self.current_type,
                        self.operator,
                        1.0000
                    )
                )
            if self.rightClicked == True or (self.click_shift_mode == True and self.rightClicked == False):
                # 右键或者按shift
                t_label = self.grabcut_loadLabel(
                    Rect_mask_Label(
                        QRectF(self.pointNormalized(self.mapToScene(event.pos()) / self._scale), QSizeF(0, 0)),
                        self.mapToScene(self.rect()).boundingRect(),
                        self.microImgRectF(),
                        QColor(255, 255, 255),
                        QColor(255, 255, 255),
                        self.current_type,
                        self.operator,
                        1.0000
                    )
                )


        if self.zoomMode == zoomMode.ZoomIn:
            self.zoomIn()
        elif self.zoomMode == zoomMode.ZoomOut:
            self.zoomOut()

        if self.scrawCursor:
            if self.allowScraw:
                self.scrawCursor.setVisible(True)
                if self.rightClicked:
                    self.updateScrawCursor(QColor(255, 255, 255))

                if not self.rightClicked and self.is_bgcolor:
                    self.erase_points = [self.mapToScene(event.pos()) / self._scale]
                    for label in self.labelList:
                        if isinstance(label, ScrawLabel) and label.Die == False:
                            label.eraser = True
                            label.point_list = self.erase_points
                            label.update()
                if self.erasermode or self.click_shift_mode:
                    self.erase_points = [self.mapToScene(event.pos()) / self._scale]
                    for label in self.labelList:
                        if isinstance(label, ScrawLabel) and label.Die == False:
                            label.eraser = True
                            label.point_list = self.erase_points
                            label.update()
            elif self.allowAiScraw:
                self.scrawCursor.setVisible(True)
                if self.rightClicked:
                    self.updateScrawCursor(QColor(255, 255, 255))

                if not self.rightClicked and self.is_bgcolor:
                    self.erase_points = [self.mapToScene(event.pos()) / self._scale]
                    for label in self.labelList:
                        if isinstance(label, ScrawLabel) and label.Die == False:
                            label.eraser = True
                            label.point_list = self.erase_points
                            label.update()
                if self.erasermode or self.click_shift_mode:
                    self.erase_points = [self.mapToScene(event.pos()) / self._scale]
                    for label in self.labelList:
                        if isinstance(label, ScrawLabel) and label.Die == False:
                            label.eraser = True
                            label.point_list = self.erase_points
                            label.update()
            else:
                self.scrawCursor.setVisible(False)

        if hasattr(self, "rectCutText") and self.rectCutText:
            rb = self.mapFromScene(QPoint(self.rectCut.rect.left()+self.rectCut.rect.width(), self.rectCut.rect.top()+self.rectCut.rect.height()) * self._scale)
            self.rectCutText.setPlainText(f'{int(self.rectCut.rect.width())} × {int(self.rectCut.rect.height())}')
            self.rectCutText.setPos(QPoint(self.rectCut.left(), self.rectCut.top()) + QPoint(0, -40) * self.rectCutText.scale())
            self.confirmButton.move(rb + QPoint(-100, 10))
            self.cancelButton.move(rb + QPoint(-50, 10))

        # ctrlstate为1时进入多选标注，将多选的标注加入到多选列表multiplechoicelist中，并给多选选中的标注增添选中效果
        if self.mainWin.ctrl_state:
            labelList = self.getLabelList()
            for x in range(0, len(labelList)):
                # print(labelList[x].isSelected())
                if labelList[x].isSelected() == 1 and labelList[x] not in self.multiplechoicelist:
                    self.multiplechoicelist.append(labelList[x])
                    # print(self.multiplechoicelist)
        else:
            self.multiplechoicelist = []

        labelList = self.multiplechoicelist
        for x in range(0, len(labelList)):
            labelList[x].setSelected(True)

        if self.allowRuler and self.mutex.tryLock():
            self.rulerLabel = self.ruler_loadLabel(
                RulerLabel(
                    self.mapToScene(self.rect()).boundingRect(),
                    self.microImgRectF()
                )
            )

        self.viewport().update()
        super(MainGraphicsView, self).mousePressEvent(event)
        # 近邻标注
        if type(self.selectedlabel) == PolygonCurveLabel:
            self.selectedlabel.setSelected(True)


    def set_waiting_win(self, status: bool, info: str = None):
        if status:
            self.waitingWin = WaitingWin(cancelEnable=False)
            if info:
                self.waitingWin.update_tip_info(info)
            self.waitingWin.show()
        else:
            if self.__dict__.get('waitingWin') and self.waitingWin:
                self.waitingWin.close()

    def set_waiting_win_without_cancel(self, status: bool, info: str = None):
        if status:
            self.waitingWin = WaitingWin(cancelEnable=False)
            if info:
                self.waitingWin.update_tip_info(info)
            self.waitingWin.setWindowModality(Qt.WindowModality.ApplicationModal)
            self.waitingWin.show()
        else:
            if self.__dict__.get('waitingWin') and self.waitingWin:
                self.waitingWin.close()

    def load_model(self):
        if self.net is None:
            if self.allowAIMagic and self.is_bgcolor == False and self.ai_model == "经典方法":
                self.load_ritm()

    def load_efficientvit_model(self):
        if self.EfficientvitSAM_predictor is None:
            self.load_efficientvit_model_thread = CommonThread(self.creat_efficientvit_sam_model, {})
            self.load_efficientvit_model_thread.signal_result.connect(lambda res: self.set_waiting_win_without_cancel(False))
            self.load_efficientvit_model_thread.signal_error.connect(lambda msg: alertError(self, mainMessage='加载模型失败', subMessage=msg))
            self.load_efficientvit_model_thread.signal_error.connect(lambda: self.set_waiting_win_without_cancel(False))
            self.load_efficientvit_model_thread.finished.connect(self.load_efficientvitSAM)
            self.set_waiting_win_without_cancel(True, "加载智能分割模型，首次加载速度较慢...")
            self.load_efficientvit_model_thread.start()
            print("加载efficientvit_sam_predictor成功")
        else:
            self.load_efficientvitSAM()

    def creat_efficientvit_sam_model(self):
        # todo 规划模型读取路径
        model = "l1"
        # weight_url = "wisdom_store/src/utils/efficientvit/weights/l1.pt"
        # weight_url = r"E:\File\historyfile\File\pycharmproject\wisdom\wisdom_store\src\utils\efficientvit\weights\l1.pt"
        # weight_url = r"D:\Project\PycharmProject\WisdomStore\wisdom_store\src\utils\efficientvit\weights\l1.pt"
        # weight_url = r"E:\USTB\WisdomStore\wisdomstore\wisdom_store\src\utils\efficientvit\weights\l1.pt"
        #weight_url = r"F:\chenyongfeng\wisdom\WisdomStore\wisdom_store\src\utils\efficientvit\weights\l1.pt"
        # 增加自动解析模型路径功能
        dirList = [r"D:\Project\PycharmProject\WisdomStore\wisdom_store\src\utils\efficientvit\weights",r'E:\USTB\WisdomStore\wisdomstore\wisdom_store\src\utils\efficientvit\weights',r'F:\chenyongfeng\wisdom\WisdomStore\wisdom_store\src\utils\efficientvit\weights']
        path = os.path.dirname(self.config.exeFilePath) + "/models"
        dirList.append(path)
        if len(self.config.exeFilePath) == 0:  # 针对源码运行模型，且启动文件不是WisdomStore.py的情况
            path = os.path.join(os.getcwd().split('WisdomStore')[0], 'WisdomStore', 'models')
            dirList.append(path)
        selected_path = None
        for dirpath in dirList:
            if os.path.exists(os.path.join(dirpath, 'l1.pt')):
                selected_path = dirpath
                break
        if selected_path is None:
            raise Exception(f"请确认以下任意文件夹中是否存在l1.pt模型文件：{dirList}")
        print(f"加载智能标注模型：{os.path.join(selected_path, 'l1.pt')}")
        weight_url = os.path.join(selected_path, 'l1.pt')

        t3 = time.time()
        self.EfficientvitSAM_predictor = efficientvit_build_model(model, weight_url)
        t4 = time.time()
        print("当前模型加载时间为", t4 - t3)
        return self.EfficientvitSAM_predictor

    def load_efficientvitSAM(self):
        # self.set_current_img()
        #creat efficientvitSAM instance
        if self.EfficientvitSAM_instance == None:
            # 创建实例
            self.EfficientvitSAM_instance = EfficientvitSAM()
            self.create_efficientvitSAM()
        else:
            self.create_efficientvitSAM()
        self.efficientvitSAM_set_encoder()

    def efficientvitSAM_set_encoder(self):
        # 如果创建了EfficientvitSAM实例，则进行图像编码
        if self.EfficientvitSAM_instance is None:
            print("EfficientvitSAM not loaded")
        if self.EfficientvitSAM_instance is not None:
            self.create_efficientvitSAM_encoder()

    def EfficientvitSAM_instance_clear_point(self):
        self.EfficientvitSAM_instance = EfficientvitSAM()
        self.EfficientvitSAM_instance.efficientvit_get_predictor(self.EfficientvitSAM_predictor)
        self.EfficientvitSAM_instance.efficientvit_set_img(self.image_EfficientvitSAM)

    def create_efficientvitSAM(self):
        self.EfficientvitSAM_instance.efficientvit_get_predictor(self.EfficientvitSAM_predictor)
        self.EfficientvitSAM_instance.efficientvit_set_img(self.image_EfficientvitSAM)

    def EfficientvitSAM_undo(self):
        if self.allowAIMagic:
            self.EfficientvitSAM_instance.efficientvit_undo()

    def EfficientvitSAM_redo(self):
        if self.allowAIMagic:
            self.EfficientvitSAM_instance.efficientvit_redo()


    def update_model(self):
        # 目前没啥用，用于多个模型切换的功能
        if self.allowAIMagic:
            if self.allowAIMagic and self.is_bgcolor == False and self.ai_model == "经典方法":
                self.load_ritm()
            elif self.allowAIMagic and self.is_bgcolor == False and self.ai_model == "FastSAM":
                self.load_fastsam()
        elif self.allowGrabCut:
            if self.is_bgcolor == False and self.ai_model == "FastSAM":
                self.load_fastsam()

    def set_current_img(self):
        if self.imgArray.shape[2] == 4:
            # 新增RGBA2RGB转换
            self.imgArray = cv2.cvtColor(self.imgArray, cv2.COLOR_BGRA2BGR)
        self.image_RITM = self.imgArray
        # self.image_fastsam = self.imgArray
        # self.image_EfficientSAM = self.imgArray.transpose(2, 0, 1)[None].astype(np.float32) / 255.0
        self.image_EfficientvitSAM = self.imgArray
        image = self.imgArray
        self.RITM_result_mask = np.zeros(image.shape[:2], dtype=np.uint16)
        # self.fastsam_result_mask = np.zeros(image.shape[:2], dtype=np.uint16)
        print("set_current_img")

    def set_model(self):
        self.device = 'cuda:0' if torch.cuda.is_available() else 'cpu'
        # path = '../utils/RITM/weights'
        # path = './models'
        dirList = [r'E:\File\historyfile\File\pycharmproject\wisdom\models']
        path = os.path.dirname(self.config.exeFilePath) + "/models"
        dirList.append(path)
        if len(self.config.exeFilePath) == 0:  # 针对源码运行模型，且启动文件不是WisdomStore.py的情况
            path = os.path.join(os.getcwd().split('WisdomStore')[0], 'WisdomStore', 'models')
            dirList.append(path)
        # dirList = [path, r'D:\File\pycharmproject\wisdom\wisdom_store\src\utils\RITM\weights']

        selected_path = None
        for dirpath in dirList:
            if os.path.exists(os.path.join(dirpath, 'coco_lvis_h18_baseline.pth')):
                selected_path = dirpath
                break
        if selected_path is None:
            raise Exception(f"请确认以下任意文件夹中是否存在coco_lvis_h18_baseline.pth模型文件：{dirList}")
        checkpoint_path = utils.find_checkpoint(selected_path, 'coco_lvis_h18_baseline.pth')
        print(f"加载智能标注模型：{os.path.join(selected_path, 'coco_lvis_h18_baseline.pth')}")
        self.net = utils.load_is_model(checkpoint_path, self.device, cpu_dist_maps=True)


    def efficientvitSAM_set_predictor(self):
        # 设定模型
        self.EfficientvitSAM_instance.efficientvit_get_predictor(self.EfficientvitSAM_predictor)
    def efficientvitSAM_set_input_point(self):
        # 设定输入点
        label = 1 #default label
        if self.rightClicked == False:
            if self.click_shift_mode is False:
                self.is_positive = True
                label = 1
            else:
                self.is_positive = False
                label = 0
        if self.rightClicked == True:
            self.is_positive = False
            label = 0
        y = self.AIMagicEfficientvitSAMPoint.toPoint().y()
        x = self.AIMagicEfficientvitSAMPoint.toPoint().x()
        # point = []
        # point.append([x,y,label])
        point = [x,y,label]
        self.EfficientvitSAM_instance.efficientvit_set_input_point(point)
    def create_efficientvitSAM_encoder(self):
        self.efficientvitSAM_img_encoder_thread = CommonThread(self.EfficientvitSAM_instance.efficientvit_build_img_encoder, {})
        self.efficientvitSAM_img_encoder_thread.signal_result.connect(lambda res: self.set_waiting_win_without_cancel(False))
        self.efficientvitSAM_img_encoder_thread.signal_error.connect(lambda msg: alertError(self, mainMessage='生成图像编码失败', subMessage=msg))
        self.efficientvitSAM_img_encoder_thread.signal_error.connect(lambda: self.set_waiting_win_without_cancel(False))
        self.efficientvitSAM_img_encoder_thread.finished.connect(self.create_efficientvitSAM_encoder_finish)
        self.set_waiting_win_without_cancel(True, "正在生成图像编码...")
        self.efficientvitSAM_img_encoder_thread.start()

    def create_efficientvitSAM_encoder_finish(self):
        self.efficientvitSAM_enable = True
        print("create_efficientvitSAM_encoder_finish")

    def efficientvitSAM_output_decoder(self):
        mask = self.EfficientvitSAM_instance.efficientvit_output_decoder()
        return mask

    def EfficientvitSAM_mouse_houver_fun(self):
        # 悬浮模式函数
        if self.efficientvitSAM_enable is True:
            if self.allowAIMagic and self.is_bgcolor == False:
                if self.EfficientvitSAM_predictor is None:
                    print("efficientvit_sam 模型未解析")
                if self.EfficientvitSAM_predictor is not None:
                    if self.EfficientvitSAM_instance is None:
                        print("EfficientvitSAM_instance not created")
                    if self.EfficientvitSAM_instance is not None:
                        self.EfficientvitSAM_mouse_houver_thread = CommonThread(self.update_mask_mouse_houver_EfficientvitSAM, {})
                        self.EfficientvitSAM_mouse_houver_thread.signal_result.connect(lambda res: self.update_EfficientvitSAM_hover_label(res[0]))
                        # if self.count%10 == 0:
                        #     print('启动鼠标悬浮',self.count)
                        # self.count += 1
                        self.EfficientvitSAM_mouse_houver_thread.start()


    def update_EfficientvitSAM_click_label(self, mask_image):
        # 点击模式
        # MouseClickScraw_label = self.getLabel(self.current_type, 'Scraw')
        # if MouseClickScraw_label is None and self.is_bgcolor == False:
        #     MouseClickScraw_label = self.addNewScrawLabel()
        #     MouseClickScraw_label.setInteract(False)
        # MouseClickScraw_label.maskToPixmap(mask_image)

        if self.rightClicked == False and self.click_shift_mode == False:
            MouseClickScraw_label = self.getLabel(self.current_type, 'Scraw')
            if MouseClickScraw_label is None and self.is_bgcolor == False:
                MouseClickScraw_label = self.addNewScrawLabel()
                MouseClickScraw_label.setInteract(False)
            MouseClickScraw_label.addMaskToPixmap(mask_image)
        else:
            MouseClickScraw_label = self.getLabel(self.current_type, 'Scraw')
            if MouseClickScraw_label is None and self.is_bgcolor == False:
                MouseClickScraw_label = self.addNewScrawLabel()
                MouseClickScraw_label.setInteract(False)
            MouseClickScraw_label.interMaskToPixmap(mask_image)

    def update_EfficientvitSAM_hover_label(self,mask_image):
        # 悬浮模式
        # 抉择：要能撤回还是要能预览
        # MouseHoverScraw_label = self.getLabel(self.current_type, 'MouseHoverScraw')
        MouseHoverScraw_label = self.getLabel(self.current_type, 'Scraw')
        if MouseHoverScraw_label is None and self.is_bgcolor == False:
            MouseHoverScraw_label = self.addNewScrawLabel()
            MouseHoverScraw_label.setInteract(False)
        MouseHoverScraw_label.maskToPixmap_hover(mask_image)
        # if self.rightClicked == False and self.click_shift_mode == False:
        #     MouseClickScraw_label = self.getLabel(self.current_type, 'Scraw')
        #     if MouseClickScraw_label is None and self.is_bgcolor == False:
        #         MouseClickScraw_label = self.addNewScrawLabel()
        #         MouseClickScraw_label.setInteract(False)
        #     MouseClickScraw_label.addMaskToPixmap_hover(mask_image)
        # else:
        #     MouseClickScraw_label = self.getLabel(self.current_type, 'Scraw')
        #     if MouseClickScraw_label is None and self.is_bgcolor == False:
        #         MouseClickScraw_label = self.addNewScrawLabel()
        #         MouseClickScraw_label.setInteract(False)
        #     MouseClickScraw_label.interMaskToPixmap_hover(mask_image)

    def update_EfficientvitSAM_hover_click_label(self, mask_image):
        # 悬浮模式下的点击
        # MouseHoverClickScraw_label = self.getLabel(self.current_type, 'MouseHoverScraw')
        MouseHoverClickScraw_label = self.getLabel(self.current_type, 'Scraw')
        if MouseHoverClickScraw_label is None and self.is_bgcolor == False:
            MouseHoverClickScraw_label = self.addNewScrawLabel()
            MouseHoverClickScraw_label.setInteract(False)
        MouseHoverClickScraw_label.maskToPixmap(mask_image)
        # if self.rightClicked == False and self.click_shift_mode == False:
        #     MouseClickScraw_label = self.getLabel(self.current_type, 'Scraw')
        #     if MouseClickScraw_label is None and self.is_bgcolor == False:
        #         MouseClickScraw_label = self.addNewScrawLabel()
        #         MouseClickScraw_label.setInteract(False)
        #     MouseClickScraw_label.addMaskToPixmap(mask_image)
        # else:
        #     MouseClickScraw_label = self.getLabel(self.current_type, 'Scraw')
        #     if MouseClickScraw_label is None and self.is_bgcolor == False:
        #         MouseClickScraw_label = self.addNewScrawLabel()
        #         MouseClickScraw_label.setInteract(False)
        #     MouseClickScraw_label.interMaskToPixmap(mask_image)


    def update_mask_mouse_houver_EfficientvitSAM(self):
        # 悬浮模式生成悬浮预览的mask
        y = self.efficientvitSAM_y
        x = self.efficientvitSAM_x
        image = self.image_EfficientvitSAM
        y_max = image.shape[0]
        x_max = image.shape[1]
        # 后续添加alt键表示负点
        if self.efficientvitSAM_enable == False:
            mask = np.full((y_max, x_max), False)
        else:
            if self.EfficientvitSAM_instance.point_coords == []:
                # 第一个点，只能是正点
                if 0 < x < x_max and 0 < y < y_max:
                    # 如果在区域内，正常用
                    self.EfficientvitSAM_instance.efficientvit_set_current_point([x, y, 1])
                    mask = self.EfficientvitSAM_instance.efficientvit_output_current_decoder()
                else:
                    # 如果出界，返回空
                    mask = np.full((y_max, x_max), False)
            else:
                # 如果不是第一个点，松开alt是正，按住alt是负
                if 0 < x < x_max and 0 < y < y_max:
                    # 第二个点，在区域内
                    if self.click_shift_mode is False:
                        # 松开alt（旧点加最新正点）
                        self.EfficientvitSAM_instance.efficientvit_set_current_point([x, y, 1])
                        mask = self.EfficientvitSAM_instance.efficientvit_output_current_decoder()
                    else:
                        # 按住alt（旧点加最新负点）
                        self.EfficientvitSAM_instance.efficientvit_set_current_point([x, y, 0])
                        mask = self.EfficientvitSAM_instance.efficientvit_output_current_decoder()
                else:
                    # 第二个点，在区域外，返回没点之前的mask（旧点，不加最新点）
                    mask = self.EfficientvitSAM_instance.efficientvit_output_decoder()
        return mask

    def update_mask_Hover_click_EfficientvitSAM(self):
        mask = self.EfficientvitSAM_instance.efficientvit_output_decoder()
        return mask

    def multimask_up(self):
        self.EfficientvitSAM_instance.multmask_level += 1
        if self.EfficientvitSAM_instance.multmask_level > 2:
            self.EfficientvitSAM_instance.multmask_level = 2

    def multimask_down(self):
        self.EfficientvitSAM_instance.multmask_level -= 1
        if self.EfficientvitSAM_instance.multmask_level < 0:
            self.EfficientvitSAM_instance.multmask_level = 0


    def set_predictor(self):
        # 预测参数，这里先写死
        zoomin_params = {
            'skip_clicks': -1,
            'target_size': (400, 400),
            'expansion_ratio': 1.4
        }
        predictor_params = {
            'brs_mode': 'NoBRS',
            'prob_thresh': 0.5,
            'zoom_in_params': zoomin_params,
            'predictor_params': {
                'net_clicks_limit': None,
                'max_size': 800  # 似乎大小有要求限制
            },
            'brs_opt_func_params': {'min_iou_diff': 1e-3},
            'lbfgs_params': {'maxfun': 20}
        }
        if predictor_params is not None:
            self.predictor_params = predictor_params
        self.predictor = get_predictor(self.net, device=self.device,
                                       **self.predictor_params)
        if self.image_RITM is not None:
            self.predictor.set_input_image(self.image_RITM)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        '''
        鼠标移动事件
        '''
        super().mouseMoveEvent(event)
        s = event.localPos()
        g = self.mapToScene(s.x(), s.y()) / self._scale
        # print('mouse move in view')
        # print("mouse pos: ", s)
        # print("global pos: ", self.mapToGlobal(s.toPoint()))
        # print("scene pos: ", self.mapToScene(s.toPoint()))
        # print(self.undoStack.count())
        if self.labelList and self.updatePixel:
            self.getPixelInformation(self.mapToScene(s.toPoint()))

        # 智慧剪刀
        if hasattr(self, 'allowIntelligentScissors') and self.allowIntelligentScissors:
            self.creatinglabel = self.WhichCreating()
            s = event.localPos()
            self.square_pos = s
            self.print_square_coordinates()
            self.viewport().update()  # Request a repaint
        else:
            self.square_pos = None
            self.viewport().update()  # Request a repaint
        if hasattr(self, 'allowIntelligentScissors') and self.allowIntelligentScissors and self.scissors and self.creatinglabel != None:
            s = event.localPos()
            g = self.mapToScene(s.x(), s.y())/self._scale
            x=g.x()-self.g3.x()
            y=g.y()-self.g3.y()
            while len(self.creatinglabel.polygon) > self.count:
                self.creatinglabel.polygon.remove(len(self.creatinglabel.polygon) - 1)
                self.creatinglabel.prectl.remove(len(self.creatinglabel.prectl) - 1)
                self.creatinglabel.nexctl.remove(len(self.creatinglabel.nexctl) - 1)
                self.creatinglabel.pointNum=self.creatinglabel.pointNum-1
            if self.g3.x()<g.x()<self.g4.x() and self.g3.y()<g.y()< self.g4.y():
                if self.hasMap and 0 <= x < self.src.shape[1] and 0 <= y < self.src.shape[0]:  # 检查鼠标是否在图像范围内
                    contour = self.tool.getContour((int(x), int(y)))  # 获取轮廓
                    self.contours = [contour]
                x=0
                for point in self.contours:
                    for i in point:
                        for j in i:
                            x=x+1
                            if x%self.ScissorspPointNum==0:
                                newPoint = self.creatinglabel.pointNormalized(
                                    QPointF(j[0] + self.g3.x(), j[1] + self.g3.y()))
                                while len(self.creatinglabel.polygon) > self.creatinglabel.pointNum:
                                    self.creatinglabel.polygon.remove(len(self.creatinglabel.polygon) - 1)
                                    self.creatinglabel.prectl.remove(len(self.creatinglabel.prectl) - 1)
                                    self.creatinglabel.nexctl.remove(len(self.creatinglabel.nexctl) - 1)
                                self.creatinglabel.polygon.append(newPoint)
                                self.creatinglabel.prectl.append(newPoint)
                                self.creatinglabel.nexctl.append(newPoint)
                                self.creatinglabel.pointNum = self.creatinglabel.pointNum + 1
                newPoint = self.creatinglabel.pointNormalized(g)
                self.creatinglabel.polygon.append(newPoint)
                self.creatinglabel.prectl.append(newPoint)
                self.creatinglabel.nexctl.append(newPoint)
                self.creatinglabel.pointNum = self.creatinglabel.pointNum + 1
                self.creatinglabel.focusedPointIndex = self.creatinglabel.pointNum
                #print(self.creatinglabel.focusedPointIndex)
                #print(len(self.creatinglabel.polygon))
            else:
                newPoint = self.creatinglabel.pointNormalized(g)
                self.creatinglabel.polygon.append(newPoint)
                self.creatinglabel.prectl.append(newPoint)
                self.creatinglabel.nexctl.append(newPoint)
                self.creatinglabel.pointNum = self.creatinglabel.pointNum + 1
                self.creatinglabel.focusedPointIndex = self.creatinglabel.pointNum
                pass
        
        # 近邻标注
        if self.quick and self.polygon_quick_clicknum==0:
            flag = False
            
            #移动点放大
            for i in range(len(self.selectedlabel.polygon)):
                t_point = self.selectedlabel.polygon.value(i)
                t_dist = (g.x() - t_point.x()) ** 2 + (g.y() - t_point.y()) ** 2
                if t_dist <= (self.selectedlabel.h_diameter / 2) ** 2:
                    self.selectedlabel.hoverPointIndex = i
                    flag = True
                    self.selectedlabel.update()
                    self.update()
                    #print(i)
                    break
            if not flag:
                self.selectedlabel.hoverPointIndex = None
                self.selectedlabel.update()
                self.update()

        if self.quick ==True and self.point1!=None and self.polygon_quick_clicknum == 1:#并且要point1不为空才行
            m = self.selectedlabel.h_diameter*self.selectedlabel.h_diameter#灵敏度
            p = None
            g = self.mapToScene(s.x(), s.y()) / self._scale
            for PtWithFlag in self.selectedlabel.points_with_flags:
                point = QPointF(PtWithFlag.point)
                n = (point.x() - g.x()) ** 2 + (point.y() - g.y()) ** 2
                if n <= m:
                    m = n
                    p = PtWithFlag
            if p == None:
                self.creatinglabel.quicking = False
                self.creatinglabel.quicked = False
                pass
            else:
                point = QPointF(p.point)
                self.creatinglabel.quicking = True
                pnum=self.selectedlabel.CheckPointNum(point)
                #print(self.p1num)
                #print(pnum)
                while len(self.creatinglabel.polygon) > self.cre_num_bef_quick:
                    self.creatinglabel.polygon.remove(len(self.creatinglabel.polygon) - 1)
                    self.creatinglabel.prectl.remove(len(self.creatinglabel.prectl) - 1)
                    self.creatinglabel.nexctl.remove(len(self.creatinglabel.nexctl) - 1)
                    self.creatinglabel.pointNum=self.creatinglabel.pointNum-1
                    self.update()
                #self.creatinglabel.quicked_points_list_end_polygon=[]
                #self.creatinglabel.quicked_points_list_end_prectl=[]
                #self.creatinglabel.quicked_points_list_end_nextctl=[]
                #下面的if为沿着++方向
                #else为沿着--方向
                if self.p1num==pnum:
                    newPoint = self.selectedlabel.polygon.value(self.p1num)
                    #newPointprectl = self.selectedlabel.prectl.value(self.p1num)
                    #newPointnexctl = self.selectedlabel.nexctl.value(self.p1num)
                    self.creatinglabel.polygon.append(newPoint)
                    self.creatinglabel.prectl.append(newPoint)
                    self.creatinglabel.nexctl.append(newPoint)
                    self.creatinglabel.pointNum = self.creatinglabel.pointNum + 1

                    newPoint = self.pointNormalized(g)
                    self.creatinglabel.polygon.append(newPoint)
                    self.creatinglabel.prectl.append(newPoint)
                    self.creatinglabel.nexctl.append(newPoint)
                    self.creatinglabel.pointNum = self.creatinglabel.pointNum + 1

                    self.creatinglabel.focusedPointIndex=-1
                    self.update()
                elif self.cal_pol_quick_dir(self.p1num,pnum):
                    self.creatinglabel.prectl.remove(self.p1num_crealabel)
                    self.creatinglabel.nexctl.remove(self.p1num_crealabel)
                    newPointprectl = self.selectedlabel.prectl.value(self.p1num)
                    newPointnexctl = self.selectedlabel.nexctl.value(self.p1num)
                    self.creatinglabel.prectl.insert(self.p1num_crealabel, newPointprectl)
                    self.creatinglabel.nexctl.insert(self.p1num_crealabel, newPointnexctl)
                    i=self.p1num+1
                    while 1:
                        i=i%self.selectedlabel.pointNum
                        if i!=pnum:
                            newPoint = self.selectedlabel.polygon.value(i)
                            newPointprectl = self.selectedlabel.prectl.value(i)
                            newPointnexctl = self.selectedlabel.nexctl.value(i)
                            self.creatinglabel.polygon.append(newPoint)
                            self.creatinglabel.prectl.append(newPointprectl)
                            self.creatinglabel.nexctl.append(newPointnexctl)
                            self.creatinglabel.pointNum = self.creatinglabel.pointNum + 1
                            i=i+1
                            self.temp_ptnum=len(self.creatinglabel.polygon)
                        else:
                            break
                    newPoint = self.selectedlabel.polygon.value(pnum)
                    newPointprectl = self.selectedlabel.prectl.value(pnum)
                    newPointnexctl = self.selectedlabel.nexctl.value(pnum)
                    self.creatinglabel.polygon.append(newPoint)
                    self.creatinglabel.prectl.append(newPointprectl)
                    self.creatinglabel.nexctl.append(newPoint)
                    self.creatinglabel.pointNum = self.creatinglabel.pointNum + 1
                    newPoint = self.pointNormalized(g)
                    self.creatinglabel.polygon.append(newPoint)
                    self.creatinglabel.prectl.append(newPoint)
                    self.creatinglabel.nexctl.append(newPoint)
                    self.creatinglabel.pointNum = self.creatinglabel.pointNum + 1
                    self.creatinglabel.focusedPointIndex=-1
                    self.update()
                else:
                    self.creatinglabel.prectl.remove(self.p1num_crealabel)
                    self.creatinglabel.nexctl.remove(self.p1num_crealabel)
                    newPointprectl = self.selectedlabel.nexctl.value(self.p1num)
                    newPointnexctl = self.selectedlabel.prectl.value(self.p1num)
                    self.creatinglabel.prectl.insert(self.p1num_crealabel, newPointprectl)
                    self.creatinglabel.nexctl.insert(self.p1num_crealabel, newPointnexctl)
                    j=self.p1num-1
                    while 1:
                        j = j % self.selectedlabel.pointNum
                        if j!=pnum:
                            newPoint = self.selectedlabel.polygon.value(j)
                            newPointprectl = self.selectedlabel.nexctl.value(j)
                            newPointnexctl = self.selectedlabel.prectl.value(j)
                            self.creatinglabel.polygon.append(newPoint)
                            self.creatinglabel.prectl.append(newPointprectl)
                            self.creatinglabel.nexctl.append(newPointnexctl)
                            self.creatinglabel.pointNum = self.creatinglabel.pointNum + 1
                            j=j-1
                            self.temp_ptnum=len(self.creatinglabel.polygon)
                        else:
                            break
                    newPoint = self.selectedlabel.polygon.value(pnum)
                    newPointprectl = self.selectedlabel.nexctl.value(pnum)
                    newPointnexctl = self.selectedlabel.prectl.value(pnum)
                    self.creatinglabel.polygon.append(newPoint)
                    self.creatinglabel.prectl.append(newPointprectl)
                    self.creatinglabel.nexctl.append(newPoint)
                    self.creatinglabel.pointNum = self.creatinglabel.pointNum + 1

                    newPoint = self.pointNormalized(g)
                    self.creatinglabel.polygon.append(newPoint)
                    self.creatinglabel.prectl.append(newPoint)
                    self.creatinglabel.nexctl.append(newPoint)
                    self.creatinglabel.pointNum = self.creatinglabel.pointNum + 1
                    self.creatinglabel.focusedPointIndex=-1
                    self.update()
        
        if self.magnifying == True:
            s = event.localPos()
            g = self.mapToScene(s.x(), s.y())
            g_pos_x = g.x()
            g_pos_y = g.y()
            self.magnifyingGlass.updatePos(g_pos_x, g_pos_y)

        if len(self.erase_points):
            self.erase_points.append(self.mapToScene(event.pos()) / self._scale)
            for label in self.labelList:
                if isinstance(label, ScrawLabel) and label.Die == False:
                    label.painting = False
                    label.point_list = self.erase_points
                    label.update()


        if self.allowAIMagic and self.Hovermode:
            point = self.pointNormalized(self.mapToScene(s.toPoint()) / self._scale)
            self.efficientvitSAM_x = point.toPoint().x()
            self.efficientvitSAM_y = point.toPoint().y()
            x = self.efficientvitSAM_x
            y = self.efficientvitSAM_y
            # print('x', x, 'y', y)

        if self.allowAIMagic and self.Hovermode:
            scraw_label = self.getLabel(self.current_type, 'Scraw')
            if scraw_label is not None:
                scraw_label.hoverMoveEvent(event)

        if self.scrawCursor:
            if self.allowScraw:
                self.scrawCursor.setVisible(True)
                # print(self.click_shift_mode)
                if self.rightClicked or self.erasermode or self.click_shift_mode:
                    self.updateScrawCursor(QColor(255, 255, 255))
                else:
                    self.updateScrawCursor()
                # if not self.rightClicked:
                #     self.updateScrawCursor()
                # else:
                #     self.updateScrawCursor(QColor(255, 255, 255))
            elif self.allowAiScraw:
                self.scrawCursor.setVisible(True)
                if self.rightClicked or self.erasermode or self.click_shift_mode:
                    self.updateScrawCursor(QColor(255, 255, 255))
                else:
                    self.updateScrawCursor()
                # if not self.rightClicked:
                #     self.updateScrawCursor()
                # else:
                #     self.updateScrawCursor(QColor(255, 255, 255))
            else:
                self.scrawCursor.setVisible(False)

        if hasattr(self, "rectCutText") and self.rectCutText:
            rb = self.mapFromScene(QPoint(self.rectCut.rect.left()+self.rectCut.rect.width(), self.rectCut.rect.top()+self.rectCut.rect.height()) * self._scale)
            self.rectCutText.setPlainText(f'{int(self.rectCut.rect.width())} × {int(self.rectCut.rect.height())}')
            self.rectCutText.setPos(QPoint(self.rectCut.left(), self.rectCut.top()) + QPoint(0, -40) * self.rectCutText.scale())
            self.confirmButton.move(rb + QPoint(-100, 10))
            self.cancelButton.move(rb + QPoint(-50, 10))

    def confirmCrop(self):
        original_image = imgPixmapToNmp(self.origImg)
        cropped_image = original_image[int(self.rectCut.rect.top()) : int(self.rectCut.rect.top() + self.rectCut.rect.height()),
                                        int(self.rectCut.rect.left()) : int(self.rectCut.rect.left() + self.rectCut.rect.width()),
                                        :]
        self.microImg = nmpToImgPixmap(cropped_image)
        self.microImgItem.setPixmap(self.microImg)
        self.rectCut.Die = True
        self.rectCut.setVisible(False)
        self.myScene.removeItem(self.rectCutText)
        self.rectCutText = None
        self.confirmButton.hide()
        self.cancelButton.hide()
        self.setCursor(QCursor(Qt.ArrowCursor))
        self.mainWin.imgEnhanced()
        self.labelCreateFinished.emit(True)

    def cancelCrop(self):
        self.rectCut.Die = True
        self.rectCut.setVisible(False)
        self.myScene.removeItem(self.rectCutText)
        self.rectCutText = None
        self.confirmButton.hide()
        self.cancelButton.hide()
        self.setCursor(QCursor(Qt.ArrowCursor))
        self.allowRectCut = False
        self.labelCreateFinished.emit(True)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        '''
        鼠标松开
        '''
        s = event.localPos()
        if self.scrawCursor:
            if self.allowScraw:
                self.scrawCursor.setVisible(True)
                if self.rightClicked:
                    self.rightClicked = False
                    self.updateScrawCursor()
            elif self.allowAiScraw:
                self.scrawCursor.setVisible(True)
                if self.rightClicked:
                    self.rightClicked = False
                    self.updateScrawCursor()
            else:
                self.scrawCursor.setVisible(False)

        for label in self.labelList:
            if isinstance(label, ScrawLabel) and label.Die == False:
                label.eraser = False
                label.update()

        if len(self.erase_points):
            self.erase_points.clear()
            for label in self.labelList:
                if isinstance(label, ScrawLabel) and label.Die == False:
                    label.point_list.clear()
                    label.painting = True

        # 普通模式下的点击操作
        if self.allowAIMagic and self.Clickmode and self.is_bgcolor == False and self.ai_model == "efficientvitsam":
            if self.EfficientvitSAM_instance is None:
                print("EfficientvitSAM Model not loaded")
                return super().mouseReleaseEvent(event)
            if self.EfficientvitSAM_instance is not None:
                # 获取坐标
                self.AIMagicEfficientvitSAMPoint = s
                self.AIMagicEfficientvitSAMPoint = self.pointNormalized(self.mapToScene(self.AIMagicEfficientvitSAMPoint.toPoint()) / self._scale)
                self.efficientvitSAM_set_input_point()
                self.EfficientvitSAM_thread = CommonThread(self.efficientvitSAM_output_decoder, {})
                self.EfficientvitSAM_thread.signal_result.connect(lambda res: self.update_EfficientvitSAM_click_label(res[0]))
                self.EfficientvitSAM_thread.signal_result.connect(lambda res: self.set_waiting_win_without_cancel(False))
                self.set_waiting_win_without_cancel(True, "正在生成掩膜结果...")
                self.EfficientvitSAM_thread.start()
                # 下面是生成反馈点的函数
                if self.rightClicked == False and self.click_shift_mode == False:
                    # 左键 且不按alt
                    point_feedback_label = self.loadLabel(
                        Feedback_PointLabel(
                            self.pointNormalized(self.mapToScene(event.pos()) / self._scale),
                            self.mapToScene(self.rect()).boundingRect(),
                            self.microImgRectF(),
                            QColor(255, 255, 255),
                            self.current_color,
                            self.current_type,
                            self.operator,
                            1.0000
                        )
                    )
                    #self.pushAddStack(point_feedback_label)
                if self.rightClicked == True or (self.click_shift_mode == True and self.rightClicked == False):
                    # 右键 或者按住alt左键
                    point_feedback_label = self.loadLabel(
                        Feedback_PointLabel(
                            self.pointNormalized(self.mapToScene(event.pos()) / self._scale),
                            self.mapToScene(self.rect()).boundingRect(),
                            self.microImgRectF(),
                            QColor(255, 255, 255),
                            QColor(255, 255, 255),
                            self.current_type,
                            self.operator,
                            1.0000
                        )
                    )
                    #self.pushAddStack(point_feedback_label)
                print("EfficientvitSAM execute success")
                return super().mouseReleaseEvent(event)

        # 悬浮模式下的点击操作
        if self.allowAIMagic and self.Hovermode and self.is_bgcolor == False:
            if self.EfficientvitSAM_predictor is None:
                print("EfficientvitSAM model not loaded")
                return super().mouseReleaseEvent(event)
            if self.EfficientvitSAM_predictor is not None:
                self.AIMagicEfficientvitSAMPoint = s
                self.AIMagicEfficientvitSAMPoint = self.pointNormalized(self.mapToScene(self.AIMagicEfficientvitSAMPoint.toPoint()) / self._scale)
                self.efficientvitSAM_set_input_point()
                self.EfficientvitSAM_Hover_click_thread = CommonThread(self.update_mask_Hover_click_EfficientvitSAM, {})
                self.EfficientvitSAM_Hover_click_thread.signal_result.connect(lambda res: self.update_EfficientvitSAM_hover_click_label(res[0]))
                self.EfficientvitSAM_Hover_click_thread.start()
                # 下面是生成反馈点的函数
                if self.rightClicked == False and self.click_shift_mode == False:
                    # 左键 且不按alt
                    point_feedback_label = self.loadLabel(
                        Feedback_PointLabel(
                            self.pointNormalized(self.mapToScene(event.pos()) / self._scale),
                            self.mapToScene(self.rect()).boundingRect(),
                            self.microImgRectF(),
                            QColor(255, 255, 255),
                            self.current_color,
                            self.current_type,
                            self.operator,
                            1.0000
                        )
                    )
                    #self.pushAddStack(point_feedback_label)
                if self.rightClicked == True or (self.click_shift_mode == True and self.rightClicked == False):
                    # 右键 或者按住alt左键
                    point_feedback_label = self.loadLabel(
                        Feedback_PointLabel(
                            self.pointNormalized(self.mapToScene(event.pos()) / self._scale),
                            self.mapToScene(self.rect()).boundingRect(),
                            self.microImgRectF(),
                            QColor(255, 255, 255),
                            QColor(255, 255, 255),
                            self.current_type,
                            self.operator,
                            1.0000
                        )
                    )
                    #self.pushAddStack(point_feedback_label)
                print("EfficientvitSAMSAM execute success")
                return super().mouseReleaseEvent(event)

        return super().mouseReleaseEvent(event)

        # if self.allowGrabCut and self.is_bgcolor == False:
        #     self.grabCutEdp = s
        #     self.grabCutStp = self.pointNormalized(self.mapToScene(self.grabCutStp.toPoint()) / self._scale)
        #     self.grabCutEdp = self.pointNormalized(self.mapToScene(self.grabCutEdp.toPoint()) / self._scale)
        #     scraw_label = self.getLabel(self.current_type, 'Scraw')
        #     if scraw_label is None and self.is_bgcolor == False:
        #         scraw_label = self.addNewScrawLabel()
        #         scraw_label.setInteract(False)
        #     x1 = min(self.grabCutStp.toPoint().x(), self.grabCutEdp.toPoint().x())
        #     x2 = max(self.grabCutStp.toPoint().x(), self.grabCutEdp.toPoint().x())
        #     y1 = min(self.grabCutStp.toPoint().y(), self.grabCutEdp.toPoint().y())
        #     y2 = max(self.grabCutStp.toPoint().y(), self.grabCutEdp.toPoint().y())
        #     rect = [x1, y1, x2 - x1, y2 - y1]
        #     if self.grabcut_flag == False:
        #         if rect[2] > 0 and rect[3] > 0:
        #             mask = grabcut_fun(self.imgArray, rect, self.grabcut_iter_count)
        #             scraw_label.maskToPixmap(mask)
        #             self.grabcut_flag = True
        #     if self.rightClicked == False and self.grabcut_flag == True:
        #         if rect[2] > 0 and rect[3] > 0:
        #             mask = grabcut_fun(self.imgArray, rect, self.grabcut_iter_count)
        #             scraw_label.addMaskToPixmap(mask)
        #     if self.rightClicked == True and self.grabcut_flag == True:
        #         if rect[2] > 0 and rect[3] > 0:
        #             mask = grabcut_fun(self.imgArray, rect, self.grabcut_iter_count)
        #             scraw_label.delMaskToPixmap(mask)

    def update_ritm_label(self, mask_image):
        scraw_label = self.getLabel(self.current_type, 'Scraw')
        scraw_label.maskToPixmap(mask_image)
        # scraw_label.addMaskToPixmap(mask_image)

    # def update_fastsam_label(self, mask_image):
    #     scraw_label = self.getLabel(self.current_type, 'Scraw')
    #     scraw_label.maskToPixmap(mask_image)
    #     # scraw_label.addMaskToPixmap(mask_image)

    def leaveEvent(self, event):
        # print('鼠标移出了')
        self.getPixelInformation()

    def setLabelsInteract(self, flag=False):
        '''
        将标注设置为是否可以交互
        '''
        self.labelInteract = flag
        labelList = self.getLabelList()
        for label in labelList:
            if type(label) != ScrawLabel and type(label) != MouseHoverScrawLabel:
                label.setInteract(flag)

    def setLabelsAllowMove(self, flag=False):
        '''
        将标注设置为是否可以移动
        '''
        labelList = self.getLabelList()
        for label in labelList:
            if type(label) != ScrawLabel:
                label.allowMove = flag

    def changeScrawMode(self, scraw):
        '''
        切换是否处于涂鸦的状态，涂鸦标注与线形标注生成方式不同于此
        '''
        flag = False
        labelList = self.getLabelList()
        if scraw:
            for label in labelList:
                if label.type == self.current_type and type(label) == ScrawLabel and label.Die == False:
                    label.setZValue(1000)
                    label.setInteract(True)
                    flag = True
                else:
                    label.setZValue(label.zValue() - 1)
                    label.setInteract(False)
        else:
            for label in labelList:
                if type(label) == ScrawLabel or type(label) == MouseHoverScrawLabel:
                    label.setZValue(-1000)
                    label.setInteract(False)
                    label.prepareGeometryChange()
                else:
                    label.setInteract(True)
                    label.prepareGeometryChange()

        if not flag and scraw and self.is_bgcolor == False:
            self.addNewScrawLabel()
        return flag

    def getLabel(self, type, labelClass):
        '''
        根据标注类别和标注类型返回一个符合条件的标注对象
        '''
        for label in self.labelList:
            if label.type == type and label.labelClass == labelClass and label.Die == False:
                return label
        return None

    def getAllLabels(self, type, labelClass):
        '''
        根据标注类别和标注类型返回一个符合条件的标注对象
        '''
        labels = []
        for label in self.labelList:
            if label.type == type and label.labelClass == labelClass and label.Die == False:
                labels.append(label)
        return labels

    def addNewScrawLabel(self, type=None):
        '''
        按照当前类别生成一个新的涂鸦层
        '''
        if type is None:
            type = self.current_type
        self.singleAddLabelNum.emit(type, "Scraw")
        t_pixmap = QPixmap(self.microImg.width(), self.microImg.height())
        t_pixmap.fill(Qt.transparent)
        t_label = self.loadLabel(ScrawLabel(t_pixmap, None, self.microImg, QColor(255, 255, 255),
                                            self.current_color, type, self.operator, 1.0000))
        t_label.penWidth = self.scrawCursor.cursorWidth
        t_label.setInteract(True)
        t_label.prepareGeometryChange()
        return t_label

    def addNewMouseHoverScrawLabel(self, type=None):
        '''
        按照当前类别生成一个新的涂鸦层
        '''
        if type is None:
            type = self.current_type
        t_pixmap = QPixmap(self.microImg.width(), self.microImg.height())
        t_pixmap.fill(Qt.transparent)
        t_label = self.loadLabel(MouseHoverScrawLabel(t_pixmap, None, self.microImg, QColor(255, 255, 255),
                                                      self.current_color, type, self.operator, 1.0000))
        t_label.penWidth = self.scrawCursor.cursorWidth
        t_label.setInteract(True)
        t_label.prepareGeometryChange()
        return t_label

    def startHoverTimer(self):
        # 启动悬浮式标注
        print("启动定时器")
        self.hovertimer = QTimer(self)
        self.count = 0
        self.hovertimer.timeout.connect(lambda: self.EfficientvitSAM_mouse_houver_fun())
        if torch.cuda.is_available():
            # 有显卡0.1s刷新
            self.hovertimer.start(100)
        else:
            # 无显卡0.25s刷新
            self.hovertimer.start(250)

    def endHoverTimer(self):
        # 结束悬浮式标注
        try:
            self.hovertimer.stop()
            self.EfficientvitSAM_mouse_houver_thread.terminate()
            print("结束")
        except:
            print("未启动悬浮线程")

    def changeLabelThres(self, thres, labelClass):
        '''
        更改涂鸦置信度阈值
        '''
        if labelClass not in ['Scraw', 'Rectangle']:  # 暂时只支持涂鸦与矩形标注
            return
        for label in self.labelList:
            for _class in self.project.classes:
                if label.type == _class['type'] and label.labelClass == labelClass and label.Die == False:
                    label.changeConfThres(thres)

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        '''
        键盘响应事件，有一些快捷键
        '''
        if event.key() == Qt.Key_Control:
            self.ZoomMode = True
        if (event.key() == Qt.Key_Equal) and (event.modifiers() == Qt.ControlModifier):
            self.zoomIn()
        if (event.key() == Qt.Key_Minus) and (event.modifiers() == Qt.ControlModifier):
            self.zoomOut()
        if event.key() == Qt.Key_Shift:
            self.horiWheel = True
            self.click_shift_mode = True
            for label in self.labelList:
                if label.isSelected() and isinstance(label, PolygonCurveLabel):
                    label.modifing = True
    # TODO 快捷键alt
        if event.key() == Qt.Key_Alt:
            print('alt1')
            self.vertiWheel = True
            for label in self.labelList:
                if label.isSelected() and isinstance(label, PolygonCurveLabel):
                    label.addCtl = True
        if event.key() == Qt.Key_Shift:
            self.click_shift_mode = True

        #A修改
        if event.key() == Qt.Key_V and event.modifiers() == Qt.ShiftModifier and not self.showCenters:
            self.showCenters = True
            for label in self.labelList:
                if isinstance(label, (RectLabel, PolygonCurveLabel, CircleLabel)) and not label.Die:
                    label.showCenterPoints(True)  # 调用标注类的方法显示中心点
                    label.setLabelVisibility(False)  # 隐藏标注框
                    label.update()
            self.viewport().update()  # 触发 paintEvent
            event.accept()
            return
        super().keyPressEvent(event)

        if event.key() == Qt.Key_Delete and (event.modifiers() == Qt.NoModifier):
            for label in self.labelList:
                if label.isSelected() == True:
                    label.Die = True
                    label.setVisible(False)
                    self.pushDeleteStack(label)
                    self.singleSubLabelNum.emit(label.type, label.labelClass)
            self.needSaveItem.emit(True)
            self.labelNumChanged.emit()
        super(MainGraphicsView, self).keyPressEvent(event)

    def keyReleaseEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() == Qt.Key_Control:
            self.ZoomMode = False
        if event.key() == Qt.Key_Shift:
            self.horiWheel = False
            self.click_shift_mode = False
            self.updateScrawCursor()
            # for label in self.labelList:
            #     if label.focused == True and isinstance(label, PolygonCurveLabel):
            #         label.modifing = False
            #         label.clearModify()
        if event.key() == Qt.Key_Alt:
            print('alt2')
            self.vertiWheel = False
            for label in self.labelList:
                if isinstance(label, PolygonCurveLabel):
                    label.addCtl = False

        #A修改
        if event.key() == Qt.Key_V and self.showCenters:
            self.showCenters = False
            for label in self.labelList:
                if isinstance(label, (RectLabel, PolygonCurveLabel, CircleLabel)) and not label.Die:
                    label.showCenterPoints(False)  # 调用标注类的方法隐藏中心点
                    label.setLabelVisibility(True)  # 恢复标注框的可见性
                    label.update()
            self.viewport().update()
            event.accept()
            return
        super().keyReleaseEvent(event)


    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        '''
        鼠标滚轮事件
        '''
        if self.allowScraw:
            if event.angleDelta().y() < 0:
                self.changeScrawPenSize.emit(False)
            else:
                self.changeScrawPenSize.emit(True)
        elif self.inferCompleted:
            if event.angleDelta().y() < 0:
                self.changeThresholdValue.emit(False)
            else:
                self.changeThresholdValue.emit(True)
        # todo 滚轮调节预览尺度
        elif self.allowAIMagic == True and self.ZoomMode == False and self.Hovermode:
            if event.angleDelta().y() < 0:
                self.multimask_down()
            else:
                self.multimask_up()
        elif self.allowAIMagic == True and self.ZoomMode == False:
            if self.Hovermode is False and self.Clickmode is False and self.allowGrabCut is False:
                if event.angleDelta().y() < 0:
                    self.changeScrawPenSize.emit(False)
                else:
                    self.changeScrawPenSize.emit(True)
        elif self.allowIntelligentScissors:
            delta = event.angleDelta().y() / 120  # 120 is the standard for one step of the wheel
            self.square_size += delta * 10  # Adjust the scaling factor as needed
            self.square_size = max(40, self.square_size)  # Set a minimum size limit
            self.square_size= min(512,self.square_size) #最大
            self.print_square_coordinates()
            self.viewport().update()  # Request a repaint
        elif self.ZoomMode == True:
            if event.angleDelta().y() < 0:
                self.zoomOut()
            else:
                self.zoomIn()
        elif self.horiWheel == True:
            horizontal_bar = self.horizontalScrollBar()
            delta_y = - event.angleDelta().y()
            v = horizontal_bar.value() + delta_y
            v = max(min(v, horizontal_bar.maximum()), horizontal_bar.minimum())  # 限制横向滚动条的value值。
            horizontal_bar.setValue(v)
        elif self.vertiWheel == True:
            # super(MainGraphicsView, self).wheelEvent(event)
            vertical_bar = self.verticalScrollBar()
            delta_x = - event.angleDelta().x()
            v = vertical_bar.value() + delta_x
            v = max(min(v, vertical_bar.maximum()), vertical_bar.minimum())  # 限制横向滚动条的value值。
            vertical_bar.setValue(v)
        else:
            vertical_bar = self.verticalScrollBar()
            delta_y = - event.angleDelta().y()
            v = vertical_bar.value() + delta_y
            v = max(min(v, vertical_bar.maximum()), vertical_bar.minimum())
            vertical_bar.setValue(v)

        self.adjustSceneRect()
        if self.allowScraw:
            self.updateScrawCursor()

    def setLabelHide(self, type, show):
        '''
        将对应类别的标注隐藏/显示
        '''
        for label in self.labelList:
            if label.type == type and not label.Die:
                label.setVisible(show)

    def setLabelHideTarget(self, id, show):
        '''
        将对应id的标注隐藏或显示
        '''
        for label in self.labelList:
            if label.id == id:
                label.setVisible(show)

    def setScale(self, scale, moveCenter=False):
        '''
        设置整个视图与所有标注的scale尺度
        '''
        center = self.mapToScene(QPoint(self.viewport().width() / 2, self.viewport().height() / 2)) / self._scale
        # center = QPointF(self.microImg.width() / 2, self.microImg.height() / 2)
        if moveCenter:
            mPos = self.mapToScene(self.mapFromGlobal(QCursor.pos())) / self._scale
            center = mPos
        # print(center)
        super(MainGraphicsView, self).setScale(scale)
        self.adjustSceneRect()
        self.setViewCenter(center)

        self.scaleChanged.emit(self._scale * 100)
        self.updateBirdView()
        if self.scrawCursor:
            self.scrawCursor.imgScale = scale
        if self.magnifyingGlass:
            self.magnifyingGlass.microImg = self.microImg.scaled(int(self.microImg.width() * scale),
                                                                 int(self.microImg.height() * scale))

    def getPixelInformation(self, sPos: QPointF = None):
        '''
        生成像素值、坐标值
        '''
        if sPos is None:
            s = ''
        else:
            s = ''
            pixelPos = sPos / self._scale
            if int(round(pixelPos.y())) < 0 or int(round(pixelPos.y())) > self.imgArray.shape[0] - 1:
                s = ''
            elif int(round(pixelPos.x())) < 0 or int(round(pixelPos.x())) > self.imgArray.shape[1] - 1:
                s = ''
            else:
                x = max(min(int(round(pixelPos.x())), self.imgArray.shape[1] - 1), 0)
                y = max(min(int(round(pixelPos.y())), self.imgArray.shape[0] - 1), 0)
                if self.imgArray.shape[-1] == 3:
                    r, g, b = self.imgArray[y, x]
                    s = 'x,y = ({}, {}), r,g,b = ({}, {}, {})'.format(x, y, r, g, b)
                elif self.imgArray.shape[-1] == 1:
                    gray = self.imgArray[y, x]
                    s = '({}, {}), {}'.format(x, y, gray)
        self.pixelString.emit(s)

    def fitScreen(self):
        '''
        视图自适应窗口大小
        '''
        if self.origImg.width() > self.origImg.height():
            self.setScale(self.viewport().width() / self.origImg.width())
        else:
            self.setScale(self.viewport().height() / self.origImg.height())

    def fullScreen(self):
        '''
        视图覆盖整个窗口大小
        '''
        if self.origImg.width() > self.origImg.height():
            self.setScale(self.viewport().height() / self.origImg.height())
        else:
            self.setScale(self.viewport().width() / self.origImg.width())

    def zoomIn(self):
        '''
        缩小
        '''
        t_scale = min(self._scale + 0.25, 5)
        self.setScale(t_scale, True)

    def zoomOut(self):
        '''
        放大
        '''
        t_scale = max(self._scale - 0.25, 0.25)
        self.setScale(t_scale, True)

    def changeLabel(self, old, new, color):
        '''
        更改标注类别或者颜色
        '''
        for label in self.labelList:
            if label.type == old:
                label.type = new
                if type(color) != QColor:
                    color = QColor(color)
                label.backColor = color
                label.updateColor()
                label.update()

    def deleteLabel(self, type):
        '''
        删除此类别标注，也就只是将其隐藏然后将Die设为True
        '''
        for label in self.labelList:
            if label.type == type:
                label.Die = True
                label.setVisible(False)
        self.viewport().update()

    def deleteLabelClass(self, str):
        '''
        删除此类型标注，也就只是将其隐藏然后将Die设为True
        '''
        for label in self.labelList:
            if label.labelClass == str:
                label.Die = True
                label.setVisible(False)
        self.viewport().update()

    def deleteSelectedLabel(self, index=None, saveScrawFlag=False):
        '''
        删除labelList中处于index下标的标注，index为None则删除当前选中的标注，也就只是将其隐藏然后将Die设为True
        '''
        if index is None:
            for label in self.labelList:
                if label.isSelected() == True:
                    label.Die = True
                    label.setVisible(False)
                    self.pushDeleteStack(label)
                    self.singleSubLabelNum.emit(label.type, label.labelClass)
        else:
            count = 0
            labelList = self.getValidLabelList()
            for label in labelList:
                if count == index:
                    if saveScrawFlag and label.labelClass == "Scraw":
                        label.clearScraw()
                    else:
                        label.Die = True
                        label.setVisible(False)
                        # self.labelList.remove(label)
                        self.pushDeleteStack(label)
                        self.singleSubLabelNum.emit(label.type, label.labelClass)
                    break
                count += 1
        self.needSaveItem.emit(True)
        self.labelNumChanged.emit()

    def labelSelected(self):
        '''
        返回当前被选中的标注对象
        '''
        for label in self.labelList:
            if label.isSelected() == True:
                return label
        return None

    def changeLabelClass(self, cls_, index=None):
        '''
        更改第index下标标注的类别和颜色
        '''
        if index is None:
            selectedLabel = self.labelSelected()
        else:
            count = 0
            labelList = self.getValidLabelList()
            for label in labelList:
                if count == index:
                    selectedLabel = label
                    break
                count += 1
        if selectedLabel:
            self.singleSubLabelNum.emit(selectedLabel.type, selectedLabel.labelClass)
            self.singleAddLabelNum.emit(cls_['type'], selectedLabel.labelClass)
            selectedLabel.type = cls_['type']
            selectedLabel.backColor = QColor(cls_['color'])
            selectedLabel.updateColor()
            selectedLabel.update()
            self.labelNumChanged.emit()

    def changePenSize(self, value):
        '''
        更改涂鸦画笔大小
        '''
        for label in self.labelList:
            if type(label) == ScrawLabel:
                label.penWidth = value
                label.updateColor()

    def changeAlpha(self, alpha):
        '''
        更该标注透明度
        '''
        self.alpha = alpha
        for label in self.labelList:
            label.alpha = alpha
            label.updateColor()
            label.update()

    def changeAlphaSelect(self, alpha):
        '''
        更改标注被选中之后的透明度
        '''
        self.alphaSelect = alpha
        for label in self.labelList:
            label.alphaSelect = alpha
            label.updateColor()
            label.update()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super(MainGraphicsView, self).resizeEvent(event)
        self.updateBirdView()
        self.adjustSceneRect()

    def clear(self):
        '''
        清空视图中的所有标注，但是labelList中还在
        '''
        for item in self.items:
            if isinstance(item, MagnifyingGlass):
                continue
            elif isinstance(item, ScrawCursor):
                continue
            else:
                self.myScene.removeItem(item)
    def clearlabel(self):
        for label in self.labelList:
                self.singleSubLabelNum.emit(label.type,label.labelClass)
                label.Die = True
                label.setVisible(False)
        self.viewport().update()

    def loadLabel(self, t_label):
        '''
        载入标注，显示到视图中
        '''
        super().loadLabel(t_label)
        if isinstance(t_label, ScrawLabel):
            t_label.painted.connect(lambda oldmap, pixmap: self.pushPaintStack(t_label, oldmap, pixmap))
            self.labelNumChanged.emit()
        elif isinstance(t_label, PointLabel):
            t_label.posChanged.connect(lambda src, dst: self.pushMoveStack(t_label, src, dst))
            t_label.IsMoving.connect(lambda: self.changeMagnify(True))
            t_label.MovingDone.connect(lambda: self.changeMagnify(False))
            t_label.creatingSuccess.connect(self.singleAddLabelNum.emit)
        elif isinstance(t_label, TagLabel):
            self.labelNumChanged.emit()
            if not hasattr(t_label, 'creating'):
                self.afterCreating(t_label)
        else:
            t_label.posChanged.connect(lambda src, dst: self.pushMoveStack(t_label, src, dst))
            t_label.creatingSuccess.connect(self.singleAddLabelNum.emit)
        t_label.updateAlpha(self.alpha)
        t_label.updateAlphaSelect(self.alphaSelect)
        t_label.updateColor()
        # self.labelNumChanged.emit()
        if (self.allowCircle or self.allowLine or self.allowPoint or self.allowPolygon or self.allowRect
            or self.allowTag or self.allowText or self.allowRectCut or self.allowIntelligentScissors) and hasattr(t_label,'creating') and t_label.creating:
            self.labelCreateFinished.emit(False)
        t_label.creatingFinish.connect(self.afterCreating)
        # t_label.creatingInterrupt.connect(self.afterCreating)
        return t_label

    def ruler_loadLabel(self, t_label):
        t_label.setScale(self._scale)
        self.myScene.addItem(t_label)
        t_label.rulerCreatingSuccess.connect(self.rulerCreatingSuccess.emit)
        t_label.MovingDone.connect(lambda: self.changeMagnify(False))
        return t_label

    def grabcut_loadLabel(self, t_label):
        super().loadLabel_new(t_label)

        if isinstance(t_label, ScrawLabel):
            t_label.painted.connect(lambda oldmap, pixmap: self.pushPaintStack(t_label, oldmap, pixmap))
            self.labelNumChanged.emit()
        elif isinstance(t_label, PointLabel):
            t_label.posChanged.connect(lambda src, dst: self.pushMoveStack(t_label, src, dst))
            t_label.IsMoving.connect(lambda: self.changeMagnify(True))
            t_label.MovingDone.connect(lambda: self.changeMagnify(False))
        elif isinstance(t_label, TagLabel):
            self.labelNumChanged.emit()
            self.afterCreating(t_label)
        else:
            t_label.posChanged.connect(lambda src, dst: self.pushMoveStack(t_label, src, dst))

        t_label.updateAlpha(self.alpha)
        t_label.updateAlphaSelect(self.alphaSelect)
        t_label.updateColor()

        # self.labelNumChanged.emit()

        if self.allowGrabCut:
            self.labelCreateFinished.emit(False)
        t_label.creatingSuccess.connect(self.singleAddLabelNum.emit)
        t_label.creatingFinish.connect(self.afterCreating)
        t_label.creatingFinish.connect(self.grabcutremove)
        t_label.creatingFinish.connect(self.grabcut_cord)

        # 进行画框运算
        t_label.creatingFinish.connect(self.grabcutupdate)
        # t_label.creatingInterrupt.connect(self.afterCreating)
        return t_label

    def grabcutremove(self, t_label):
        self.myScene.removeItem(t_label)

    def grabcut_cord(self, t_label):
        self.grabcut_width = t_label.rect.width()
        self.grabcut_height = t_label.rect.height()
        self.grabcutx = t_label.rect.left()
        self.grabcuty = t_label.rect.top()

    def grabcutupdate(self, t_label):
        scraw_label = self.getLabel(self.current_type, 'Scraw')
        if scraw_label is None and self.is_bgcolor == False:
            scraw_label = self.addNewScrawLabel()
            scraw_label.setInteract(False)
        x = int(self.grabcutx)
        y = int(self.grabcuty)
        w = int(self.grabcut_width)
        h = int(self.grabcut_height)
        label_value = False
        # EfficientVitSAM输入xyxy
        rect = [x, y, x+w, y+h]
        self.EfficientvitSAM_instance.efficientvit_set_input_box(rect)
        if self.rightClicked == False and self.click_shift_mode == False:
            label_value = False
        else:
            label_value = True
        if label_value is False and self.grabcut_flag is False:
            # 第一次且为正标注
            self.EfficientvitSAM_Rect_thread = CommonThread(self.update_mask_EfficientvitSAM_Rect, {})
            self.EfficientvitSAM_Rect_thread.signal_result.connect(lambda res: scraw_label.addMaskToPixmap(res[0]))
            self.EfficientvitSAM_Rect_thread.start()
            self.grabcut_flag = True
        elif label_value is True and self.grabcut_flag is False:
            # 第一次且为负标注
            pass
        elif label_value is False and self.grabcut_flag is True:
            # 第二次且为负标注
            self.EfficientvitSAM_Rect_thread = CommonThread(self.update_mask_EfficientvitSAM_Rect, {})
            self.EfficientvitSAM_Rect_thread.signal_result.connect(lambda res: scraw_label.addMaskToPixmap(res[0]))
            self.EfficientvitSAM_Rect_thread.start()
        elif label_value is True and self.grabcut_flag is True:
            # 第二次且为正标注
            self.EfficientvitSAM_Rect_thread = CommonThread(self.update_mask_EfficientvitSAM_Rect, {})
            self.EfficientvitSAM_Rect_thread.signal_result.connect(lambda res: scraw_label.delMaskToPixmap(res[0]))
            self.EfficientvitSAM_Rect_thread.start()

    def update_mask_EfficientvitSAM_Rect(self):
        mask = self.EfficientvitSAM_instance.efficientvit_output_decoder_box()
        mask = mask[0]
        #mask = mask[1]
        #mask = mask[2]
        mask = mask + 0
        mask = np.uint8(mask)
        print(mask)
        return mask
        #
        # if self.grabcut_flag == False:
        #     if rect[2] > 0 and rect[3] > 0:
        #         # mask = grabcut_fun(self.imgArray, rect, self.grabcut_iter_count)
        #         # scraw_label.maskToPixmap(mask)
        #         # scraw_label.addMaskToPixmap(mask)
        #         # 修复数据缓存问题
        #         # 实现多线程
        #         dict = {'img': self.imgArray, 'rect': rect, 'iterCount': self.grabcut_iter_count}
        #         self.Grabcut_thread = CommonThread(grabcut_fun, dict)
        #         # self.Grabcut_thread.signal_result.connect(lambda res: self.grabcut_mask_thread_get(res[0]))
        #         self.Grabcut_thread.signal_result.connect(lambda res: scraw_label.addMaskToPixmap(res[0]))
        #         self.Grabcut_thread.start()
        #         self.grabcut_flag = True
        # elif self.rightClicked == False and self.grabcut_flag == True:
        #     if rect[2] > 0 and rect[3] > 0:
        #         dict = {'img': self.imgArray, 'rect': rect, 'iterCount': self.grabcut_iter_count}
        #         self.Grabcut_thread = CommonThread(grabcut_fun, dict)
        #         self.Grabcut_thread.signal_result.connect(lambda res: scraw_label.addMaskToPixmap(res[0]))
        #         self.Grabcut_thread.start()
        # elif self.rightClicked == True and self.grabcut_flag == True:
        #     if rect[2] > 0 and rect[3] > 0:
        #         dict = {'img': self.imgArray, 'rect': rect, 'iterCount': self.grabcut_iter_count}
        #         self.Grabcut_thread = CommonThread(grabcut_fun, dict)
        #         self.Grabcut_thread.signal_result.connect(lambda res: scraw_label.delMaskToPixmap(res[0]))
        #         self.Grabcut_thread.start()


    # def rect_update_mask_fastsam(self):
    #     image = self.image_fastsam
    #     everything_results = self.net(
    #         image,
    #         device=self.device,
    #         retina_masks=True,
    #         imgsz=1024,
    #         conf=0.4,
    #         iou=0.9
    #     )
    #     x = int(self.grabcutx)
    #     y = int(self.grabcuty)
    #     w = int(self.grabcut_width)
    #     h = int(self.grabcut_height)
    #     self.box_prompt = []
    #     self.box_prompt_tmp = convert_box_xywh_to_xyxy([x, y, w, h])
    #     self.box_prompt.append(self.box_prompt_tmp)
    #     prompt_process = FastSAMPrompt(image, everything_results, device=self.device)
    #     if self.box_prompt[0][2] != 0 and self.box_prompt[0][3] != 0:
    #         ann = prompt_process.box_prompt(bboxes=self.box_prompt)
    #         bboxes = self.box_prompt
    #     h, w = self.image_fastsam.shape[:2]
    #     # if len(ann) == 2:
    #     #     ann = np.logical_or(ann[0], ann[1])
    #     #     ann = np.where(ann, 1, 0)
    #     # mask_image = ann
    #     mask_image = ann[len(ann) - 1].reshape(h, w)
    #     return mask_image
    #
    # def rect_update_fastsam_label(self, mask_image):
    #     scraw_label = self.getLabel(self.current_type, 'Scraw')
    #     if scraw_label is None and self.is_bgcolor == False:
    #         scraw_label = self.addNewScrawLabel()
    #         scraw_label.setInteract(False)
    #     scraw_label.maskToPixmap(mask_image)

    def changeMagnify(self, flag):
        '''
        更改放大效果的显示或隐藏
        '''
        if self.allowPoint:
            flag = True
        self.magnifying = flag
        try:
            self.magnifyingGlass.setVisible(flag)
            g = self.mapToScene(self.mapFromGlobal(QCursor.pos()))
            self.magnifyingGlass.updatePos(g.x(), g.y())
            if flag:
                self.magnifyingGlass.setZValue(1000)
            else:
                self.magnifyingGlass.setZValue(-1000)
        except Exception as e:
            print(str(e))

    def changeZoomMode(self, flag):
        '''
        更改鼠标左键按下时进行 放大还是缩小
        '''
        if flag == zoomMode.NoZoom:
            self.zoomMode = zoomMode.NoZoom
            self.unsetCursor()
        elif flag == zoomMode.ZoomIn:
            self.zoomMode = zoomMode.ZoomIn
            pixmap = QPixmap(":/resources/放大-透明背景.png")  # pixmap 是 QPixmap()的实例化，QPixmap()类用于图片的显示
            new_pixmap = pixmap.scaled(16, 16)  # scaled方法返回自定义尺寸的副本
            cursor = QCursor(new_pixmap, 0, 0)
            self.setCursor(cursor)
        elif flag == zoomMode.ZoomOut:
            self.zoomMode = zoomMode.ZoomOut
            pixmap = QPixmap(":/resources/缩小-透明背景.png")
            new_pixmap = pixmap.scaled(16, 16)
            cursor = QCursor(new_pixmap, 0, 0)
            self.setCursor(cursor)

    def updateScrawCursor(self, color=None):
        '''
        更新涂鸦模式下鼠标形状位置
        '''
        g = self.mapToScene(self.mapFromGlobal(QCursor.pos()))
        g = QPointF(g.x() - 1.2, g.y() - 1.2)  # 修正
        try:
            if hasattr(self, "scrawCursor") and self.scrawCursor:
                if not color:
                    self.scrawCursor.updateScrawCursor(g, self.current_color)
                else:
                    self.scrawCursor.updateScrawCursor(g, color)
        except Exception as e:
            print(str(e))

    def pushAddStack(self, t_label):
        '''
        标注生成时对此操作压栈
        '''
        add = AddCommand(self, t_label)
        undoEnabledState = self.undoAction.isEnabled()
        redoEnabledState = self.redoAction.isEnabled()
        self.undoStack.push(add)
        self.undoAction.setEnabled(undoEnabledState)
        self.redoAction.setEnabled(redoEnabledState)
        # print('add')



    def pushDeleteStack(self, t_label):
        '''
        标注删除时对此操作压栈
        '''
        delete = DeleteCommand(self, t_label)
        self.undoStack.push(delete)
        # print('delete')

    def pushMoveStack(self, t_label, srcPoints, dstPoints):
        '''
        标注被移动位置时压栈
        '''
        move = MoveCommand(t_label, srcPoints, dstPoints)
        self.undoStack.push(move)
        # print('move')

    def pushPaintStack(self, t_label, oldmap, pixmap):
        '''
        涂鸦标注被修改时压栈
        '''
        move = PaintCommand(t_label, oldmap, pixmap)
        self.undoStack.push(move)
        # print('paint')

    def setCursor(self, a0) -> None:
        self.viewport().setCursor(a0)
        return super().setCursor(a0)

    def unsetCursor(self) -> None:
        # self.viewport().unsetCursor()
        return super().unsetCursor()

    def afterCreating(self, t_label):
        '''
        description: 在图形绘制之后，为了能够仅对刚刚绘制的图形做更改，而使其余图形进入不可修改的状态
        return {*}
        '''
        self.mutex.unlock()
        self.labelNumChanged.emit()
        for label in self.labelList:
            if not label == t_label:
                label.setInteract(False)
        if not self.allowRectCut:
            self.labelCreateFinished.emit(True)

        if self.allowRectCut:
            rb = self.mapFromScene(QPoint(self.rectCut.rect.left()+self.rectCut.rect.width(), self.rectCut.rect.top()+self.rectCut.rect.height()) * self._scale)
            self.confirmButton.move(rb + QPoint(-100, 10))
            self.cancelButton.move(rb + QPoint(-50, 10))
            # self.confirmButton.move(QPoint(self.rectCut.left()+self.rectCut.width(), self.rectCut.top()+self.rectCut.height()) + QPoint(-100, 50))
            # self.cancelButton.move(QPoint(self.rectCut.left()+self.rectCut.width(),self.rectCut.top()+self.rectCut.height())+ QPoint(-50, 50))
            self.confirmButton.show()
            self.cancelButton.show()
            self.setCursor(QCursor(Qt.ArrowCursor))
            self.allowRectCut = False

    '''
    description: 删除localpos所在位置的多边形的关键点。受右键菜单调用
    param {*} self
    param {*} localPos
    return {*}
    '''

    def deleteKeyPoint(self, localPos):
        find = False
        for label in self.labelList:
            if label.isSelected() and isinstance(label, PolygonCurveLabel):
                find = True
                break
        if not find:
            return
        label.deleteKeyPoint(localPos)

    '''
    description: 将多边形、矩形转换为涂鸦
    return {*}
    '''

    def convertPolygonToSraw(self):
        '''
        多边形转换为涂鸦
        '''
        if self.allowPolygon:
            labelClass = 'PolygonCurve'
        elif self.allowCircle:
            labelClass = 'Circle'
        elif self.allowRect:
            labelClass = 'Rectangle'
        else:
            return
        count = 0
        for label in self.labelList:
            if label.Die == True:
                continue
            if label.type == self.current_type and label.labelClass == labelClass and label.Die == False:
                if type(label) in [PolygonCurveLabel, RectLabel, CircleLabel]:
                    mask = label.exportMask()
                else:
                    continue
                scraw_label = self.getLabel(label.type, 'Scraw')
                if scraw_label is None and self.is_bgcolor == False:
                    scraw_label = self.addNewScrawLabel(label.type)
                    scraw_label.setInteract(False)
                self.deleteSelectedLabel(count)
                count -= 1
                scraw_label.addMaskToPixmap(mask)
                scraw_label.update()

            count += 1

    def convertScrawToPolygon(self, type=None):
        '''
        涂鸦转换为多边形
        '''
        if type is None:
            type = self.current_type
        scraw_label = self.getLabel(type, 'Scraw')
        if scraw_label is None:
            return
        # 初始化
        self.EfficientvitSAM_instance_clear_point()
        contours = scraw_label.exportContours()
        for contour in contours:
            t_label = self.loadLabel(
                PolygonCurveLabel(
                    QPolygonF(contour),
                    None,
                    None,
                    self.mapToScene(self.rect()).boundingRect(),
                    self.microImgRectF(),
                    QColor(255, 255, 255),
                    scraw_label.backColor,
                    scraw_label.type,
                    scraw_label.operator,
                    1.0000
                )
            )
            # t_label.updateAlpha(self.alpha)
            # t_label.updateAlphaSelect(self.alphaSelect)
            # t_label.updateColor()
            # self.allowPolygon = False
            if self.allowAIMagic:
                self.deleteLabelClass('Feedback')
                # 关闭悬浮
                self.endHoverTimer()
            self.singleAddLabelNum.emit(t_label.type, t_label.labelClass)
            self.labelNumChanged.emit()
            t_label.creating = False
            self.pushAddStack(t_label)
        index = self.labelList.index(scraw_label)
        count = index
        for label in self.labelList[:index]:
            if label.Die == True:
                count -= 1
        self.deleteSelectedLabel(count)

    # 近邻标注：找creatinglabel
    def WhichCreating(self):
        for label in self.labelList:
            if type(label) == PolygonCurveLabel:
                if label.creating:
                    return label
            if type(label) == IntelligentScissors:
                if label.creating:
                    return label

    #计算多边形快速标记的方向            
    def cal_pol_quick_dir(self,pointnum1,pointnum2):
        i=pointnum1
        sum1=0
        while 1:
            self.selectedlabel.pointNum = len(self.selectedlabel.polygon)
            i=i%self.selectedlabel.pointNum
            if i%self.selectedlabel.pointNum!=pointnum2:
                sum1=sum1+self.bezier_length(self.selectedlabel.polygon.value(i), self.selectedlabel.nexctl.value(i),
                                         self.selectedlabel.prectl.value((i + 1)% self.selectedlabel.pointNum), self.selectedlabel.polygon.value((i + 1)% self.selectedlabel.pointNum))
                #print("is")
                #print(i,sum1)
                i = i + 1
            else:
                break
        j=pointnum2
        sum2 = 0
        while 1:
            j = j % self.selectedlabel.pointNum
            if j % self.selectedlabel.pointNum != pointnum1:
                sum2 = sum2 + self.bezier_length(self.selectedlabel.polygon.value(j),
                                                 self.selectedlabel.nexctl.value(j),
                                                 self.selectedlabel.prectl.value((j + 1)% self.selectedlabel.pointNum),
                                                 self.selectedlabel.polygon.value((j + 1)% self.selectedlabel.pointNum))
                #print("jk")
                #print(j, sum2)
                j = j + 1
            else:
                break
        #print(sum2)
        #print(sum1)
        #print(sum2)
        if sum1<=sum2:
            #print("++")
            return True
        else:
            #print("--")
            return False
    
    # 三次贝塞尔曲线的导数
    def bezier_derivative(self,A, A1, B1, B, t):
        P_prime = (-3 * (1 - t) ** 2 * np.array(A) +
                   3 * (1 - t) ** 2 * np.array(A1) -
                   6 * t * (1 - t) * np.array(A1) +
                   6 * t * (1 - t) * np.array(B1) -
                   3 * t ** 2 * np.array(B1) +
                   3 * t ** 2 * np.array(B))
        return np.linalg.norm(P_prime)  # 返回导数的范数（长度）

    # 贝塞尔曲线的长度计算
    def bezier_length(self,A, A1, B1, B):
        # 对贝塞尔导数在[0,1]区间进行数值积分
        A=(A.x(),A.y())
        A1=(A1.x(),A1.y())
        B=(B.x(),B.y())
        B1=(B1.x(),B1.y())
        #print("A,A1,B1,B")
        #print(A,A1,B1,B)
        #print(type(A))
        length, _ = quad(lambda t: self.bezier_derivative(A, A1, B1, B, t), 0, 1)
        return length
                
    def print_square_coordinates(self):
        #计算框实时的四边位置 并修改g1 g2,在mousemove和wheelevent被调用
        if self.square_pos is not None:
            left = self.square_pos.x() - self.square_size / 2
            right = self.square_pos.x() + self.square_size / 2
            top = self.square_pos.y() - self.square_size / 2
            bottom = self.square_pos.y() + self.square_size / 2
            self.g1 = self.mapToScene(left, top) / self._scale#左上点
            self.g2 = self.mapToScene(right, bottom) / self._scale#右下点

    def paintEvent(self, event):
        #画智慧剪刀的裁剪框
        super().paintEvent(event)
        if self.square_pos is not None:
            painter = QPainter(self.viewport())
            painter.setPen(QPen(QColor(173, 216, 230)))
            square_rect = QRectF(self.square_pos.x() - self.square_size / 2,
                                 self.square_pos.y() - self.square_size / 2,
                                 self.square_size, self.square_size)
            painter.drawRect(square_rect)

class AddCommand(QUndoCommand):
    def __init__(self, graphics_view, shape):
        super(AddCommand, self).__init__()
        self.shape = shape
        self.graphic_view = graphics_view
        self.first_execution = True

    def redo(self):
        if not self.first_execution:
            if self.shape.Die:
                self.graphic_view.singleAddLabelNum.emit(self.shape.type, self.shape.labelClass)
        else:
            self.first_execution = False
        self.shape.show()
        self.shape.Die = False
        self.graphic_view.labelNumChanged.emit()
        # self.shape.setInteract(True)

    def undo(self):
        if not self.shape.Die:
            self.graphic_view.singleSubLabelNum.emit(self.shape.type, self.shape.labelClass)
        self.shape.hide()
        self.shape.Die = True
        self.graphic_view.labelNumChanged.emit()
        # self.shape.setInteract(False)


class DeleteCommand(QUndoCommand):
    def __init__(self, graphics_view, shape):
        super(DeleteCommand, self).__init__()
        self.shape = shape
        self.graphic_view = graphics_view
        self.first_execution = True

    def redo(self):
        if not self.first_execution:
            if not self.shape.Die:
                self.graphic_view.singleSubLabelNum.emit(self.shape.type, self.shape.labelClass)
        else:
            self.first_execution = False
        self.shape.hide()
        self.shape.Die = True
        self.graphic_view.labelNumChanged.emit()

    def undo(self):
        if self.shape.Die:
            self.graphic_view.singleAddLabelNum.emit(self.shape.type, self.shape.labelClass)
        self.shape.show()
        self.shape.Die = False
        self.graphic_view.labelNumChanged.emit()


class MoveCommand(QUndoCommand):
    def __init__(self, shape, src, dst):
        super(MoveCommand, self).__init__()
        self.shape = shape
        self.src = src
        self.dst = dst

    def redo(self):
        self.shape.setPoints(self.dst)

    def undo(self):
        self.shape.setPoints(self.src)


class PaintCommand(QUndoCommand):
    def __init__(self, shape, oldmap, pixmap):
        super(PaintCommand, self).__init__()
        self.shape = shape
        self.oldmap = oldmap
        self.pixmap = pixmap

    def redo(self):
        self.shape.setPixmap(self.pixmap)

    def undo(self):
        self.shape.setPixmap(self.oldmap)
