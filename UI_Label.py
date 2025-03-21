import uuid
from math import ceil, sqrt, pow
from PyQt5.QtWidgets import QGraphicsItem, QGraphicsEllipseItem, QGraphicsObject, QGraphicsPixmapItem
from PyQt5.QtGui import QCursor, QTransform, QBrush, QColor, QPen, QPainterPath, QPolygonF, QImage, QPixmap, QFont, QPainter, QFontMetrics
from PyQt5.QtCore import QRect, QRectF, QPointF, QPoint, pyqtSignal, QBuffer, QByteArray, QIODevice, QLine, QLineF
from PyQt5.QtCore import Qt
# from PyQt5.Qt import QGraphicsItem, QRectF, QFont, QPainter, \
#     QBrush, QColor, QGraphicsEllipseItem, QPen, QEvent, \
#     QPainterPath, QPoint, pyqtSignal, QGraphicsObject, \
#     QGraphicsPixmapItem, QPolygonF, QPointF, QImage, QBuffer, \
#     QByteArray, QIODevice, QPixmap
from wisdom_store.src.utils.image_transform import lblPixmapToNmp
from wisdom_store.src.utils.base64translator import numpy2ToBase64, numpyUint8ToBase64
import numpy as np
import math
import copy
from PIL import Image
import numpy as np
import random
import cv2

class Label(QGraphicsObject):
    MouseInLabelSg = pyqtSignal(bool)
    selectedItem = pyqtSignal(QGraphicsObject)
    needSaveItem = pyqtSignal(bool)
    creatingSuccess = pyqtSignal(str, str)
    creatingFinish = pyqtSignal(QGraphicsObject)
    creatingInterrupt = pyqtSignal(QGraphicsObject)
    posChanged = pyqtSignal(list, list)

    
    def __init__(self, pRect, cRect, frontColor, backColor, type, operator, confidence):
        super(Label, self).__init__()
        # self.setAcceptedMouseButtons(Qt.LeftButton)
        self.setFlag(QGraphicsObject.ItemIsSelectable, True)
        self.id = uuid.uuid1()
        self.frontColor = frontColor
        self.backColor = backColor
        self.operator = operator
        self.confidence = confidence
        self.type = type
        # 标注显示
        self.scale = 1.0
        self.alpha = 127
        self.alphaSelect = 191
        self.penWidth = 3
        self.diameter = 12  # 端点直径
        self.s_diameter = 18  # 选中时端点直径
        self.h_diameter = 24  # 悬浮时端点直径
        # 矩形范围内端点控制
        self.pRect = pRect  # 矩形区域内绘制
        self.cRect = cRect  # 矩形区域内控制位置
        # 标签显示
        self.fontPixelSize = 12
        self.fontOffset = 5
        self.threshold = 0
        # label创建
        self.pointNum = 0
        # 开关
        self.drawText = False
        self.hover = False
        self.textWidth = None
        self.focused = False
        self.adjustPoint = False
        self.adjustBorder = False
        self.adjustAll = False
        self.allowMove = False
        self.allowInteract = True
        self.Die = False
        self.hoverPointIndex = None
        self.focusedPointIndex = -1
        self.ctlPointIndex = -1
        self.rightClicked = False
        self.setAcceptHoverEvents(True)
        # 撤销重做
        self.moved = False
        self.moveSrcPoints = None
        self.moveDstPoints = None

    def boundingRect(self) -> QRectF:
        """
        用于告知graphicsView如何绘制的区域，需要包含自身
        @return:
        """
        return self.paintRect()

    def containPoint(self, point: QPointF):
        if hasattr(self, 'polygonRect') and self.polygonRect:
            pass
        else:
            points = [self.cRect.topLeft() * self.scale, self.cRect.topRight() * self.scale, self.cRect.bottomRight() * self.scale, self.cRect.bottomLeft() * self.scale]
            self.polygonRect = QPolygonF(points)
        return self.polygonRect.containsPoint(point, Qt.OddEvenFill)

    def pointNormalized(self, point: QPointF):
        x, y = 0, 0
        if point.x() < self.cRect.left():
            x = self.cRect.left()
        elif point.x() > self.cRect.right():
            x = self.cRect.right()
        else:
            x = point.x()
        if point.y() < self.cRect.top():
            y = self.cRect.top()
        elif point.y() > self.cRect.bottom():
            y = self.cRect.bottom()
        else:
            y = point.y()
        return QPointF(x, y)

    def ponitOffset(self, point: QPointF):
        dx, dy = 0, 0
        if point.x() < self.cRect.left():
            dx = self.cRect.left() - point.x()
        elif point.x() > self.cRect.right():
            dx = self.cRect.right() - point.x()

        if point.y() < self.cRect.top():
            dy = self.cRect.top() - point.y()
        elif point.y() > self.cRect.bottom():
            dy = self.cRect.bottom() - point.y()

        return dx, dy

    def posOffset(self, points: list):
        ox, oy = 0, 0
        for point in points:
            dx, dy = self.ponitOffset(point)
            if abs(ox) < abs(dx):
                ox = dx
            if abs(oy) < abs(dy):
                oy = dy
        return ox, oy


    def paintRect(self):
        """
        计算绘制范围的矩形大小
        @return:
        """
        return self.pRect

    def shape(self):
        qpath = QPainterPath()
        qpath.addRect(self.boundingRect())

        return qpath

    def text(self):
        """
        label上方需要显示的信息
        @return:
        """

        # return "{},{},{}".format(str(self.type), str(self.confidence), str(self.operator))
        return "{}".format(str(self.type))

    def hoverEnterEvent(self, event: 'QGraphicsSceneHoverEvent') -> None:
        self.hover = True
        self.updateColor()
        self.update()

    def hoverMoveEvent(self, event: 'QGraphicsSceneHoverEvent') -> None:
        self.hover = True
        self.updateColor()
        self.update()

    def hoverLeaveEvent(self, event: 'QGraphicsSceneHoverEvent') -> None:
        self.hover = False
        self.updateColor()
        self.update()

    def updateColor(self):
        """
        更新该label的颜色，因为有时候癌症类别会变、透明度会变
        @return:
        """
        self.selectPen = QPen()
        self.selectPen.setColor(self.backColor)
        self.selectPen.setWidth(self.penWidth)

        self.selectBrush = QBrush(Qt.SolidPattern)
        self.MaskColor = QColor(*self.backColor.getRgb())
        tempColor = QColor(self.MaskColor.rgba())
        if self.hover:
            tempColor.setAlpha(self.alphaSelect)
        else:
            tempColor.setAlpha(self.alpha)
        self.selectBrush.setColor(tempColor)

        dotColor = QColor(255, 255, 255)
        self.dotPen =  QPen(dotColor)
        self.dotPen.setWidth(2)
        self.dotPen.setStyle(Qt.DotLine)

        txtColor = QColor('white')
        self.textPen = QPen()
        self.textPen.setColor(txtColor)

        self.labelPen = Qt.NoPen
        self.labelBrush = QBrush(Qt.SolidPattern)
        self.labelBrush.setColor(self.backColor)

        bgColor = QColor('#252B41')
        self.labelPen1 = Qt.NoPen
        self.labelBrush1 = QBrush(Qt.SolidPattern)
        self.labelBrush1.setColor(self.backColor)

        self.labelPen2 = Qt.NoPen
        self.labelBrush2 = QBrush(Qt.SolidPattern)
        self.labelBrush2.setColor(bgColor)

        self.font = QFont()
        self.font.setPixelSize(self.fontPixelSize)

    def textRect(self, x, y):
        horizGap = 3
        verticGap = 3
        # if self.textWidth > self.width():
        #     width = max(self.width(), fPS * 6)
        # else:
        width = self.textWidth + 8 * horizGap + 1.5 * self.fontPixelSize
        # height = ceil((self.textWidth / width)) * fPS
        height = verticGap * 6 + self.fontPixelSize * 1.5

        # print(fPS,width,self.textWidth,height)
        
        rect1 = QRectF(x, y - height, width, height)
        rect2 = QRectF(x + horizGap, y - height + verticGap, width - 2 * horizGap, height - 2 * verticGap)
        rect3 = QRectF(x + 3 * horizGap, y - height + 3 * verticGap, self.fontPixelSize * 1.5, self.fontPixelSize * 1.5)
        rect4 = QRectF(x + 3 * horizGap + self.fontPixelSize * 1.5, y - height + 3 * verticGap, self.textWidth + 4 * horizGap, self.fontPixelSize * 1.5)
        return rect1, rect2, rect3, rect4

    def setScale(self, scale: float) -> None:
        self.scale = scale

    def updateAlpha(self, alpha):
        self.alpha = alpha

    def updateAlphaSelect(self, alphaSelect):
        self.alphaSelect = alphaSelect

    def setInteract(self, interact):
        self.allowMove = interact
        self.drawText = interact
        self.allowInteract = interact
        # self.focused = False
        self.setSelected(False)
        # self.setFlag(QGraphicsObject.ItemIsSelectable, interact)
        self.update()

    # def __eq__(self, other):
    #     return self.id == other.id

    def initCursor(self):
        # self.setCursor(Qt.ArrowCursor)
        self.unsetCursor()

    def getExport(self):
        dict = {}
        dict["label_class"] = self.labelClass
        dict["label_type"] = self.type
        dict["operator"] = self.operator
        dict["confidence"] = self.confidence
        return dict


class RectLabel(Label):

    def __init__(self, rect, pRect, cRect, frontColor, backColor, type, operator, confidence):
        super(RectLabel, self).__init__(pRect, cRect, frontColor, backColor, type, operator, confidence)
        self.rect = rect
        self.updateColor()
        self.labelClass = "Rectangle"
        # self.drawText = True
        if rect.isEmpty():
            self.creating = True
        # self.setFlag(QGraphicsObject.ItemIsMovable)
        self.srcPos = self.rect.topLeft()
        #A修改
        self.show_rect = True
        self.centers=[]

    #A修改
    def caculateCenter(self):
        center = self.rect.center()
        return center

    def getAllCenters(self):
        self.centers = [self.caculateCenter()]
        return self.centers

    def drawAllCenters(self, painter):
        painter.setPen(Qt.NoPen)
        painter.setBrush(self.labelBrush)
        for center in self.centers:
            painter.drawEllipse(center, 5, 5)

    def showCenterPoints(self, show):
        if show:
            self.centers = self.getAllCenters()
        else:
            self.centers = []
        self.update()

    def setLabelVisibility(self, visible):
        self.show_rect = visible
        self.setVisible(visible)
        self.update()

    def top(self):
        """
        由于self.rect保存的是原图大小下得绝对位置，需要根据graphicsView中的offset和scale重新计算显示位置的top
        @return:
        """
        return self.rect.top() * self.scale

    def left(self):
        """
        由于self.rect保存的是原图大小下得绝对位置，需要根据graphicsView中的offset和scale重新计算显示位置的left
        @return:
        """
        return self.rect.left() * self.scale

    def width(self):
        """
        由于self.rect保存的是原图大小下得绝对位置，需要根据graphicsView中的offset和scale重新计算显示位置的width
        @return:
        """
        return self.rect.width() * self.scale

    def height(self):
        """
        由于self.rect保存的是原图大小下得绝对位置，需要根据graphicsView中的offset和scale重新计算显示位置的heifht
        @return:
        """
        return self.rect.height() * self.scale

    # def boundingRect(self) -> QRectF:
    #     """
    #     用于告知graphicsView如何绘制的区域，需要包含自身
    #     @return:
    #     """
    #     # temprect = self.paintRect()
    #     # return QRectF(temprect.left()-100,temprect.top()-100,temprect.width()+2000,temprect.height()+2000)

    #     return self.paintRect()

    # def paintRect(self):
    #     """
    #     计算绘制范围的矩形大小
    #     @return:
    #     """
    #     if self.origimg:
    #         return QRectF(0, 0, self.origimg.width() * self.scale, self.origimg.height() * self.scale)
    #     else:
    #         pW = self.selectPen.width()
    #         if self.drawText:
    #             tRect = self.textZone()[0]
    #             # 此处加的offset为防止标签部分渲染擦除失效
    #             tW = tRect.width() + 20
    #             tH = tRect.height()
    #             return QRectF(self.left() - self.diameter / 2, self.top() - tH, max(self.width() + self.diameter, tW),
    #                         self.height() + tH + self.diameter)
    #         else:
    #             return QRectF(self.left() - self.diameter / 2, self.top() - self.diameter / 2, self.width() + self.diameter,
    #                         self.height() + self.diameter)
        

    def shape(self):
        """
        shape可以比boundingrect更为复杂，这里都一样了
        @return:
        """
        # pW = self.selectPen.width()
        # if self.drawText:
        #     tRect = self.textZone()
        #     tW = tRect.width()
        #     tH = tRect.height()
        #
        #
        #     return QRectF(self.left() - self.radius / 2, self.top() - tH, max(self.width() + self.radius, tW),
        #                   self.height() + tH + self.radius)
        # else:
        #     return QRectF(self.left() - self.radius / 2, self.top() - self.radius / 2, self.width() + self.radius,
        #                   self.height() + self.radius)
        temp = QPainterPath()
        temp.setFillRule(Qt.WindingFill)
        if self.creating:
            # boxRect = QRectF(0, 0, self.origimg.width() * self.scale, self.origimg.height() * self.scale)
            boxRect = self.paintRect()
            temp.addRect(boxRect)
        else:
            # boxRect = QRectF(self.left() - self.diameter / 2, self.top() - self.diameter / 2, self.width() + self.diameter,
            #                     self.height() + self.diameter)
            
            boxRect = QRectF(self.left(), self.top(), self.width(), self.height())
            temp.addRect(boxRect)
            temp.addRect(self.textZone()[0])
            if self.isSelected():
                pointList = self.pointList()
                for i in range(len(pointList)):
                    point = pointList[i]
                    temp.addEllipse(point, self.diameter / 2, self.diameter / 2)
                    if self.hoverPointIndex == i:
                        temp.addEllipse(point, self.h_diameter / 2, self.h_diameter / 2)
        return temp

    def textZone(self):
        """
        用于计算信息区域的显示范围，比如框很窄是不是需要多行显示
        @return:
        """
        fPS = self.font.pixelSize()
        if self.textWidth is None:
            self.textWidth = fPS * 4

        rect1, rect2, rect3, rect4 = self.textRect(self.left(), self.top())
        return rect1, rect2, rect3, rect4

    def pointList(self):
        pointList = [
                QPointF(self.left(), self.top()),   # 左上
                QPointF(self.left() + self.width(), self.top()),    # 右上
                QPointF(self.left(), self.top() + self.height()),   # 左下
                QPointF(self.left() + self.width(), self.top() + self.height()),    # 右下

                QPointF(self.left() + self.width() / 2, self.top()),    # 上
                QPointF(self.left(), self.top() + self.height() / 2),   # 左
                QPointF(self.left() + self.width(), self.top() + self.height() / 2),    # 右
                QPointF(self.left() + self.width() / 2, self.top() + self.height()),    # 下
            ]
        return pointList

    def paint(self, painter, option, widget):
        painter.setPen(self.selectPen)
        painter.setBrush(self.selectBrush)
        painter.setRenderHint(QPainter.Antialiasing)
        #A修改
        if self.show_rect:
            painter.drawRect(QRectF(self.left(), self.top(), self.width(), self.height()))
        self.drawAllCenters(painter)


        # 如果被选中就绘制四个角的圆圈
        # if self.focused:
        if self.isSelected():
            painter.setPen(Qt.NoPen)
            painter.setBrush(self.labelBrush)
            # painter.drawPath(self.shape())

            pointList = self.pointList()
            for i in range(len(pointList)):
                point = pointList[i]
                painter.drawEllipse(point, self.diameter / 2, self.diameter / 2)
                if self.hoverPointIndex == i:
                    painter.drawEllipse(point, self.h_diameter / 2, self.h_diameter / 2)

            # painter.drawEllipse(self.left() - self.radius / 2, self.top() - self.radius / 2, self.radius, self.radius)
            # painter.drawEllipse(self.left() + self.width() - self.radius / 2, self.top() - self.radius / 2, self.radius,
            #                     self.radius)
            # painter.drawEllipse(self.left() - self.radius / 2, self.top() + self.height() - self.radius / 2,
            #                     self.radius, self.radius)
            # painter.drawEllipse(self.left() + self.width() - self.radius / 2,
            #                     self.top() + self.height() - self.radius / 2, self.radius, self.radius)

            # painter.drawEllipse(self.left() + self.width() / 2 - self.radius / 2, self.top() - self.radius / 2, self.radius, self.radius)
            # painter.drawEllipse(self.left() - self.radius / 2, self.top() + self.height() / 2 - self.radius / 2, self.radius,
            #                     self.radius)
            # painter.drawEllipse(self.left() + self.width() / 2 - self.radius / 2, self.top() + self.height() - self.radius / 2,
            #                     self.radius, self.radius)
            # painter.drawEllipse(self.left() + self.width() - self.radius / 2,
            #                     self.top() + self.height() / 2 - self.radius / 2, self.radius, self.radius)

            t_pen = QPen(QColor(255, 255, 255))
            t_pen.setWidth(2)
            t_pen.setStyle(Qt.DotLine)
            painter.setPen(t_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(QRectF(self.left(), self.top(), self.width(), self.height()))

        # painter.setPen(QPen(Qt.black, 2, Qt.SolidLine))
        # painter.drawPath(self.shape())
        if self.drawText:
            painter.setPen(self.textPen)
            painter.setFont(self.font)
            self.textWidth = painter.fontMetrics().boundingRect(self.text()).width()

            # painter.setPen(self.labelPen)
            # painter.setBrush(self.labelBrush)
            # painter.drawRect(self.textZone())

            rect1, rect2, rect3, rect4 = self.textZone()
            painter.setPen(self.labelPen1)
            painter.setBrush(self.labelBrush1)
            painter.drawRect(rect1)

            painter.setPen(self.labelPen2)
            painter.setBrush(self.labelBrush2)
            painter.drawRect(rect2)

            painter.setPen(self.labelPen1)
            painter.setBrush(self.labelBrush1)
            painter.drawRect(rect3)

            painter.setPen(self.textPen)
            painter.setFont(self.font)
            painter.drawText(rect4, Qt.AlignCenter, self.text())

        # painter.drawEllipse(self.rect.topLeft().x()-5,self.rect.topLeft().y()-5,10,10)
        # painter.drawEllipse(self.rect.topRight().x()-5,self.rect.topRight().y()-5,10,10)

    def hoverEnterEvent(self, event: 'QGraphicsSceneHoverEvent') -> None:
        # print("hover enter&move")
        if not self.allowInteract:
            return
        super(RectLabel, self).hoverEnterEvent(event)
        self.unsetCursor()
        pass

    def hoverMoveEvent(self, event: 'QGraphicsSceneHoverEvent') -> None:
        if not self.allowInteract:
            return
        super(RectLabel, self).hoverMoveEvent(event)
        tPos = event.pos()
        if self.creating:
            nPos = self.pointNormalized(tPos / self.scale)
            x = nPos.x()
            y = nPos.y()
            topLeft = QPointF(min(self.srcPos.x(), x), min(self.srcPos.y(), y))
            bottomRight = QPointF(max(self.srcPos.x(), x), max(self.srcPos.y(), y))
            self.rect = QRectF(topLeft, bottomRight)
            self.prepareGeometryChange()
            self.update()
        elif self.isSelected() and self.allowMove:
            pindex = self.pointInPointList(tPos.x(), tPos.y())
            if pindex != -1:
                self.hoverPointIndex = pindex
                if pindex in [0, 3]:
                    self.setCursor(Qt.SizeFDiagCursor)
                elif pindex in [1, 2]:
                    self.setCursor(Qt.SizeBDiagCursor)
                elif pindex in [4, 7]:
                    self.setCursor(Qt.SizeVerCursor)
                elif pindex in [5, 6]:
                    self.setCursor(Qt.SizeHorCursor)
            elif self.pointInBox(tPos.x(), tPos.y()):
                self.setCursor(Qt.SizeAllCursor)
                self.hoverPointIndex = None
            else:
                self.hoverPointIndex = None
                event.ignore()
            self.update()

    def hoverLeaveEvent(self, event: 'QGraphicsSceneHoverEvent') -> None:
        if not self.allowInteract:
            return
        super(RectLabel, self).hoverLeaveEvent(event)
        self.unsetCursor()
        self.hoverPointIndex = None
        self.update()

    def setNew(self):
        self.i, self.j = 1, 1
        self.adjustPoint = True
        self.adjustBorder = False
        self.drawText = False
        # self.focused = True
        self.setSelected(True)
        self.selectedItem.emit(self)
        self.MouseInLabelSg.emit(True)

    def pointInPointList(self, x, y):
        pointList = self.pointList()
        for i in range(len(pointList)):
            point = pointList[i]
            if self.hoverPointIndex == i:
                diameter = self.h_diameter
            else:
                diameter = self.diameter
            if pow(x - (point.x()), 2) + pow(y - (point.y()), 2) <= pow(diameter / 2, 2):
                return i
        return -1

    def pointInBox(self, x, y):
        """
        判断点击位置是否在label的矩形框内
        @param x: 鼠标点击的x
        @param y: 鼠标点击的y
        @return:
        """
        if self.pointInRect(x, y, QRect(self.left(), self.top(), self.width(), self.height())):
            return True
        else:
            return False

    def pointInBorder(self, x, y):
        """
        判断点击位置是否在四条边上
        @param x: 鼠标点击的x
        @param y: 鼠标点击的y
        @return:
        """
        pW = self.selectPen.width()
        if self.pointInRect(x, y, QRect(self.left() - pW / 2, self.top() - pW / 2, self.width() + pW, pW)):
            return (0, 0)
        elif self.pointInRect(x, y,
                              QRect(self.left() - pW / 2, self.top() + self.height() - pW / 2, self.width() + pW, pW)):
            return (1, 0)
        elif self.pointInRect(x, y, QRect(self.left() - pW / 2, self.top() - pW / 2, pW, self.height() + pW)):
            return (0, 1)
        elif self.pointInRect(x, y,
                              QRect(self.left() + self.width() - pW / 2, self.top() - pW / 2, pW, self.height() + pW)):
            return (1, 1)
        else:
            return False

    def pointInBorderPoint(self, x, y):
        """
        判断点是否在四个角的四条边上
        @param x: 点的x
        @param y: 点的y
        @return:
        """
        pW = self.selectPen.width()
        if pow(x - (self.left() + self.width() / 2), 2) + pow(y - (self.top()), 2) <= pow(self.h_diameter / 2, 2) and self.hoverPointIndex == 4: # 上
            return (0, 0)
        elif pow(x - (self.left() + self.width() / 2), 2) + pow(y - (self.top() + self.height()), 2) <= pow(self.h_diameter / 2, 2 and self.hoverPointIndex == 7):  # 下
            return (1, 0)
        elif pow(x - (self.left()), 2) + pow(y - (self.top() + self.height() / 2), 2) <= pow(self.h_diameter / 2, 2) and self.hoverPointIndex == 5:  # 左
            return (0, 1)
        elif pow(x - (self.left() + self.width()), 2) + pow(y - (self.top() + self.height() / 2), 2) <= pow(self.h_diameter / 2, 2) and self.hoverPointIndex == 6:  # 右
            return (1, 1)
        else:
            return False

    def pointInRect(self, x, y, rect):
        """
        判断点是否在指定矩形内
        @param x: 点的x
        @param y: 点的y
        @param rect: 指定的矩形
        @return:
        """
        tRect = rect
        if x >= tRect.left() and x <= tRect.right() and y >= tRect.top() and y <= tRect.bottom():
            return True

    def pointInCircle(self, x, y):
        """
        判断点是否在四个角的圆圈中
        @param x: 点的x
        @param y: 点的y
        @return:
        """
        for i in range(2):
            for j in range(2):
                if pow(x - (self.left() + i * self.width()), 2) + pow(y - (self.top() + j * self.height()), 2) <= pow(
                        self.h_diameter / 2, 2):
                    return (i, j)
        return False

    def contourNormalized(self):
        topleft, bottomright = self.rect.topLeft(), self.rect.bottomRight()
        ox, oy = self.posOffset([topleft, bottomright])
        # topleft += QPointF(ox, oy)
        # bottomright += QPointF(ox, oy)
        self.rect.translate(ox, oy)

    def mousePressEvent(self, event) -> None:
        if not self.allowInteract:
            return
        self.selectedItem.emit(self)
        self.origRect = QRectF(self.rect)
        tPos = event.pos()
        x = tPos.x()
        y = tPos.y()
        if self.creating:
            if event.buttons() & Qt.RightButton:
                self.rightClicked = True
            else:
                self.rightClicked = False
            if self.rightClicked:
                self.Die = True
                self.hide()
                self.setInteract(False)
                self.creating = False
                # self.drawText = True
                self.update()
                self.creatingFinish.emit(self)
                # self.creatingInterrupt.emit(self)

            elif self.rect.topLeft() != self.rect.bottomRight():
                self.creatingSuccess.emit(self.type, self.labelClass) # 框形标注成功
                self.creatingFinish.emit(self)
                # self.drawText = True
                self.creating = False
                self.prepareGeometryChange()
                self.update()
                self.allowMove = True

        else:
            self.moveSrcPoints = self.getPoints()
            pindex = self.pointInPointList(tPos.x(), tPos.y())
            # 判断鼠标点击的具体位置
            # if self.pointInCircle(x, y):
            if pindex in [0, 1, 2, 3]:
                # self.i, self.j = self.pointInCircle(x, y)
                rectPointIndex = [
                    [0, 0],[1, 0],[0, 1],[1, 1]
                ]
                self.i, self.j = rectPointIndex[pindex]
                self.adjustPoint = True
                self.adjustBorder = False
                self.drawText = False
                # self.focused = True
                # self.selectedItem.emit(self)
                self.MouseInLabelSg.emit(True)
                self.setCursor(Qt.CrossCursor)
            # elif self.pointInBorderPoint(x, y):
            elif pindex in [4, 5, 6, 7]:
                # self.i, self.j = self.pointInBorderPoint(x, y)
                rectPointIndex = [
                    [0, 0],[0, 1],[1, 1],[1, 0]
                ]
                self.i, self.j = rectPointIndex[pindex - 4]
                self.adjustBorder = True
                self.adjustPoint = False
                self.drawText = False
                # self.focused = True
                # self.selectedItem.emit(self)
                self.MouseInLabelSg.emit(True)
                self.setCursor(Qt.CrossCursor)
            # elif self.pointInBox(x, y):
            else:
                # print("point In Box")
                # self.focused = True
                self.adjustPoint = False
                self.adjustBorder = False
                self.adjustAll = True
                self.lastPos = tPos
                # self.selectedItem.emit(self)
                self.MouseInLabelSg.emit(True)
            # else:
            #     # self.focused = True
            #     self.MouseInLabelSg.emit(False)
            #     event.ignore()

    def mouseMoveEvent(self, event) -> None:
        if not self.allowInteract:
            return
        tPos = event.pos()
        # event.accept()
        needsave = True
        self.moved = True
        # 移动时需要根据点击位置的不同做出不同的更新
        if self.adjustPoint:
            # print(tPos)
            # 点击的是四个角
            if self.i == 0 and self.j == 0:
                self.moveLeftTop(self.pointNormalized(tPos / self.scale))
                # print("LeftTop")
            elif self.i == 0 and self.j == 1:
                self.moveLeftBottom(self.pointNormalized(tPos / self.scale))
                # print("LeftBottom")
            elif self.i == 1 and self.j == 0:
                self.moveRightTop(self.pointNormalized(tPos / self.scale))
                # print("RightTop")
            elif self.i == 1 and self.j == 1:
                self.moveRightBottom(self.pointNormalized(tPos / self.scale))
                # print("RightBottom")
        elif self.adjustBorder:
            # 点击的是一个边
            if self.i == 0 and self.j == 0:
                self.moveTop(self.pointNormalized(tPos / self.scale))
                # print("Top")
            elif self.i == 0 and self.j == 1:
                self.moveLeft(self.pointNormalized(tPos / self.scale))
                # print("Left")
            elif self.i == 1 and self.j == 0:
                self.moveBottom(self.pointNormalized(tPos / self.scale))
                # print("Bottom")
            elif self.i == 1 and self.j == 1:
                self.moveRight(self.pointNormalized(tPos / self.scale))
                # print("Right")
        elif self.adjustAll:
            # 点击的是整体
            lPos = self.lastPos
            move = tPos - lPos
            self.lastPos = tPos
            self.rect.translate(move.x() / self.scale, move.y() / self.scale)
            self.contourNormalized()
        else:
            needsave = False

        self.update()

    def moveTop(self, pos):
        self.rect = QRectF(self.origRect.left(), pos.y(), self.origRect.width(),
                           self.origRect.bottom() - pos.y()).normalized()

    def moveRight(self, pos):
        self.rect = QRectF(self.origRect.left(), self.origRect.top(), pos.x() - self.origRect.left(),
                           self.origRect.height()).normalized()

    def moveLeft(self, pos):
        self.rect = QRectF(pos.x(), self.origRect.top(), self.origRect.right() - pos.x(),
                           self.origRect.height()).normalized()

    def moveBottom(self, pos):
        self.rect = QRectF(self.origRect.left(), self.origRect.top(), self.origRect.width(),
                           pos.y() - self.origRect.top()).normalized()

    def moveLeftTop(self, pos):
        self.rect = QRectF(pos, self.origRect.bottomRight()).normalized()

    def moveLeftBottom(self, pos):
        self.rect = QRectF(pos.x(), self.origRect.top(), self.origRect.right() - pos.x(),
                           pos.y() - self.origRect.top()).normalized()

    def moveRightTop(self, pos):
        self.rect = QRectF(self.origRect.left(), pos.y(), pos.x() - self.origRect.left(),
                           self.origRect.bottom() - pos.y()).normalized()

    def moveRightBottom(self, pos):
        self.rect = QRectF(self.origRect.topLeft(), pos).normalized()

    def mouseReleaseEvent(self, event) -> None:
        if not self.allowInteract:
            return
        # print("release:"+str(event.pos()))
        # print(str(self.rect))
        
        self.adjustPoint = False
        self.adjustBorder = False
        self.adjustAll = False
        self.MouseInLabelSg.emit(False)
        # self.needSaveItem.emit(True)
        # self.selectedItem.emit(self)
        if self.creating == False:
            self.drawText = True
        if self.moveSrcPoints and self.moved:
            self.moveDstPoints = self.getPoints()
            self.posChanged.emit(self.moveSrcPoints, self.moveDstPoints)
        self.moveSrcPoints = None
        self.moveDstPoints = None
        self.moved = False
        #A修改
        self.centers = self.getAllCenters()
        self.update()
        #     self.creatingFinish.emit()
        #     self.creating = False

    def exportMask(self):
        mask = np.zeros((int(self.cRect.height()), int(self.cRect.width())), dtype=np.uint8)
        x1 = int(self.rect.left())
        y1 = int(self.rect.top())
        x2 = int(self.rect.right())
        y2 = int(self.rect.bottom())
        pts = np.array([[x1, y1], [x2, y1], [x2, y2], [x1, y2]], np.int32)
        cv2.fillPoly(mask, [pts], color=(255))
        return mask


    def getExport(self):
        dict = super(RectLabel, self).getExport()

        dict["left"] = self.rect.left()
        dict["top"] = self.rect.top()
        dict["width"] = self.rect.width()
        dict["height"] = self.rect.height()
        return dict

    def getPoints(self):
        return [self.rect.topLeft(), self.rect.bottomRight()]

    def setPoints(self, points):
        assert len(points) == 2
        # topLeft = QPointF(min(points[0].x(), points[1].x()), min(points[0].y(), points[1].y()))
        # bottomRight = QPointF(max(points[0].x(), points[1].x()), max(points[0].y(), points[1].y()))
        self.rect = QRectF(points[0], points[1])
        self.update()

    def changeConfThres(self, thres):
        self.threshold = thres
        if self.threshold > self.confidence:
            self.setVisible(False)
        else:
            self.setVisible(True)

    def confThresEnsure(self):
        if self.threshold > self.confidence:
            self.confidence = 0
            self.setVisible(False)
            self.Die = True
        else:
            self.confidence = 1
            self.setVisible(True)
            self.Die = False
        


class PolygonCurveLabel(Label):

    def __init__(self, polygon, prectl, nexctl, pRect, cRect, frontColor, backColor, type, operator, confidence):
        super(PolygonCurveLabel, self).__init__(pRect, cRect, frontColor, backColor, type, operator, confidence)
        self.polygon = polygon
        self.prectl = prectl if prectl else QPolygonF(polygon)
        self.nexctl = nexctl if nexctl else QPolygonF(polygon)
        #A修改
        self.centers=[]
        self.show_polygon = True

        self.basePoint = self.polygon.value(0)
        self.lastPoint = self.polygon.value(0) # 指向绘制过程中最后一个鼠标悬浮点
        self.selected_index = None
        self.moving_all = False

        # self.diameter = 20
        self.addCtl = False
        self.doubleClicked = False
        self.labelClass = "PolygonCurve"
        self.updateColor()
        if self.polygon.count() <= 1:
            self.creating = True
            self.pointNum = 0
        else:
            self.pointNum = self.polygon.count()
        # 增量修改关键点
        self.modifing = False
        self.modified_list = []
        self.modified_plg = []
        self.modified_pre = []
        self.modified_nxt = []
        self.modified_num = 0

        # 用于近邻标注
        self.quicked = False
        self.points_with_flags=[]
        self.addptcount = 1
        self.quicking=False
        '''self.count =0
        self.point1 = None
        self.point2 = None
        self.p1num= -2
        self.p2num= -2'''
        self.events=[]

        self.arced = False
        self.pressed = False

    # def boundingRect(self) -> QRectF:
    #     """
    #     用于告知graphicsView如何绘制的区域，需要包含自身
    #     @return:
    #     """
    #     return self.paintRect()


    # def paintRect(self):
    #     """
    #     计算绘制范围的矩形大小
    #     @return:
    #     """
    #     return QRectF(0, 0, self.origimg.width() * self.scale, self.origimg.height() * self.scale)

    #A修改
    def caculateCenter(self):
        n = len(self.polygon)
        if n == 0:
            return QPointF(0, 0)

        total_x = sum(point.x() for point in self.polygon)
        total_y = sum(point.y() for point in self.polygon)

        return QPointF(total_x / n, total_y / n)

    def getAllCenters(self):
        self.centers = [self.caculateCenter()]
        return self.centers

    def drawAllCenters(self, painter):
        painter.setPen(Qt.NoPen)
        painter.setBrush(self.labelBrush)
        for center in self.centers:
            painter.drawEllipse(center, 5, 5)

    def showCenterPoints(self, show):
        if show:
            self.centers = self.getAllCenters()
        else:
            self.centers = []
        self.update()

    def setLabelVisibility(self, visible):
        self.show_polygon = visible
        self.setVisible(visible)
        self.update()



    def shape(self):
        """
        shape可以比boundingrect更为复杂
        @return:
        """
        temp = QPainterPath()
        temp.setFillRule(Qt.WindingFill)
        if self.creating or self.modifing and self.modified_num != 0:
            t_rect = self.polygon.boundingRect()
            temp.addRect(self.paintRect())

        else:
            polygon, prectl, nexctl = [], [], []
            for i in range(len(self.polygon)):
                polygon.append(self.polygon.value(i))
                prectl.append(self.prectl.value(i))
                nexctl.append(self.nexctl.value(i))

            if not self.clockwise(polygon): # Qt.WindingFill 与逆时针的多边形不兼容
                polygon.reverse()
                prectl.reverse()
                nexctl.reverse()
                prectl, nexctl = nexctl, prectl
            polygon = QPolygonF(polygon)
            prectl = QPolygonF(prectl)
            nexctl = QPolygonF(nexctl)

            temp.addPath(self.bezierPath(polygon, prectl, nexctl, True, self.scale))

            if self.isSelected():
                for i in range(len(self.polygon)):
                    if i == self.focusedPointIndex:
                        temp.addEllipse(self.polygon.value(i) * self.scale, self.s_diameter / 2, self.s_diameter / 2)
                    elif i == self.hoverPointIndex:
                        temp.addEllipse(self.polygon.value(i) * self.scale, self.h_diameter / 2, self.h_diameter / 2)
                    else:
                        temp.addEllipse(self.polygon.value(i) * self.scale, self.diameter / 2, self.diameter / 2)
                focusedPoint, ctlPoints = self.ctlPoints()
                for point in ctlPoints:
                    # temp.add(QLineF(point, focusedPoint))
                    temp.addEllipse(point, self.diameter / 2, self.diameter / 2)
            if self.drawText:
                temp.addRect(self.textZone()[0])
        return temp


    def textZone(self):
        """
        用于计算信息区域的显示范围
        @return:
        """
        if self.textWidth == None:
            self.textWidth = self.font.pixelSize() * 4
        for i in range(len(self.polygon)):
            if i == 0:
                textPoint = self.polygon.value(i)
            elif textPoint.y() > self.polygon.value(i).y():
                textPoint = self.polygon.value(i)
        rect1, rect2, rect3, rect4 = self.textRect(textPoint.x() * self.scale, textPoint.y() * self.scale)
        return rect1, rect2, rect3, rect4

    def bezierPath(self, polygon, prectl, nexctl, closed, scale=1):
        tpath = QPainterPath()
        tpath.setFillRule(Qt.WindingFill)
        for i in range(len(polygon)):
            if i == 0:
                tpath.moveTo(polygon.value(0) * scale)
            else:
                tpath.cubicTo(nexctl.value(i - 1) * scale, prectl.value(i) * scale, polygon.value(i) * scale)
        if closed:
            # tpath.closeSubpath()
            tpath.cubicTo(nexctl.value(len(nexctl) - 1) * scale, prectl.value(0) * scale, polygon.value(0) * scale)
        return tpath

    def clockwise(self, points_list):
        n = len(points_list)
        if n < 3:
            return 0.0
        area = 0
        for i in range(n):
            x = points_list[i].x()
            y = points_list[i].y()
            area += x * points_list[(i + 1) % n].y() - y * points_list[(i + 1) % n].x()
        return True if area > 0 else False


    def drawBezierPolyline(self, painter):
        painter.drawPath(self.bezierPath(self.polygon, self.prectl, self.nexctl, False, self.scale))


    def drawBezierPolygon(self, painter):
        painter.drawPath(self.bezierPath(self.polygon, self.prectl, self.nexctl, True, self.scale))

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(self.selectPen)
        painter.setBrush(self.selectBrush)
        # A修改
        if self.show_polygon:
            self.drawBezierPolygon(painter)
        self.drawAllCenters(painter)
        # 画蒙版与线
        if self.creating:
            # painter.drawPolyline(QPolygonF(temp_point_list))
            painter.setPen(Qt.NoPen)
            painter.setBrush(self.selectBrush)
            self.drawBezierPolygon(painter)

            painter.setPen(self.selectPen)
            painter.setBrush(Qt.NoBrush)
            self.drawBezierPolyline(painter)

        # 如果被选中就绘制每个点的圆圈
        # if self.focused:
        if self.isSelected():
            painter.setPen(Qt.NoPen)
            painter.setBrush(self.labelBrush)

            # 锚点
            temp_point_list = []
            for i in range(len(self.polygon)):
                temp_point_list.append(self.polygon.value(i) * self.scale)
            count = 0
            for point in temp_point_list:
                # if count == self.focusedPointIndex:
                #     painter.setPen(Qt.NoPen)
                #     painter.setBrush(QBrush(QColor(0, 0, 0)))
                if count == 0 and self.creating:
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(QBrush(QColor(255, 255, 255)))
                else:
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(self.labelBrush)

                if count == self.focusedPointIndex:
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(QColor(255, 255, 255))
                    painter.drawEllipse(point, self.s_diameter / 2, self.s_diameter / 2)
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(self.labelBrush)
                    painter.drawEllipse(point, self.s_diameter / 2 * 0.66, self.s_diameter / 2 * 0.66)    # focused的点扩大1.5倍,并且凸显中心点
                elif count == self.hoverPointIndex and self.creating==True and count==0:#回到初始点放大
                    painter.drawEllipse(point, self.h_diameter / 2, self.h_diameter / 2)    # hover的点扩大1.5倍
                elif count == self.hoverPointIndex and self.creating==False:
                    painter.drawEllipse(point, self.h_diameter / 2, self.h_diameter / 2)    # hover的点扩大1.5倍
                else:
                    painter.drawEllipse(point, self.diameter / 2, self.diameter / 2)
                count += 1

            # 控制点 控制线
            focusedPoint, ctlPoints = self.ctlPoints()
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255))
            for point in ctlPoints:
                painter.drawEllipse(point, self.diameter / 2, self.diameter / 2)

            painter.setPen(self.dotPen)
            painter.setBrush(Qt.NoBrush)
            for point in ctlPoints:
                painter.drawLine(QLineF(point, focusedPoint))

        # 画虚线
        # if self.focused or self.creating:
        # if self.isSelected() or self.creating:
        #     painter.setPen(self.dotPen)
        #     painter.setBrush(Qt.NoBrush)
        #     self.drawBezierPolygon(painter)
        #下面是多边形快速标记的白色虚线显示
        if self.quicked==False and self.isSelected():
            painter.setPen(self.dotPen)
            painter.setBrush(Qt.NoBrush)
            self.drawBezierPolygon(painter)
        if self.creating:
            painter.setPen(self.dotPen)
            painter.setBrush(Qt.NoBrush)
            self.drawBezierPolygon(painter)

        # 画增量修改
        if self.modifing and self.modified_num != 0:
            # 线
            painter.setPen(self.selectPen)
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(self.bezierPath(QPolygonF(self.modified_plg), QPolygonF(self.modified_pre), QPolygonF(self.modified_nxt), False, self.scale))
            # 蒙版
            painter.setPen(Qt.NoPen)
            painter.setBrush(self.selectBrush)
            painter.drawPath(self.bezierPath(QPolygonF(self.modified_plg), QPolygonF(self.modified_pre), QPolygonF(self.modified_nxt), False, self.scale))
            # 控制点、线
            focusedPoint = self.modified_plg[self.modified_num - 1]
            ctlPoints = [self.modified_pre[self.modified_num - 1], self.modified_nxt[self.modified_num - 1]]
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255))
            for point in ctlPoints:
                painter.drawEllipse(point * self.scale, self.diameter / 2, self.diameter / 2)

            painter.setPen(self.dotPen)
            painter.setBrush(Qt.NoBrush)
            for point in ctlPoints:
                painter.drawLine(QLineF(point * self.scale, focusedPoint * self.scale))

        if self.drawText:
            painter.setPen(self.textPen)
            painter.setFont(self.font)
            self.textWidth = painter.fontMetrics().boundingRect(self.text()).width()

            # painter.setPen(self.labelPen)
            # painter.setBrush(self.labelBrush)
            # painter.drawRect(self.textZone())

            # painter.setPen(self.textPen)
            # painter.setFont(self.font)
            # painter.drawText(self.textZone(), Qt.AlignCenter, self.text())
            rect1, rect2, rect3, rect4 = self.textZone()
            painter.setPen(self.labelPen1)
            painter.setBrush(self.labelBrush1)
            painter.drawRect(rect1)

            painter.setPen(self.labelPen2)
            painter.setBrush(self.labelBrush2)
            painter.drawRect(rect2)

            painter.setPen(self.labelPen1)
            painter.setBrush(self.labelBrush1)
            painter.drawRect(rect3)

            painter.setPen(self.textPen)
            painter.setFont(self.font)
            painter.drawText(rect4, Qt.AlignCenter, self.text())

    def update(self):
        super(PolygonCurveLabel, self).update()

        polygon_, prectl_, nexctl_ = [], [], []
        for i in range(len(self.polygon)):
            polygon_.append(self.polygon.value(i))
            prectl_.append(self.prectl.value(i))
            nexctl_.append(self.nexctl.value(i))

        reversed = False
        path = QPainterPath()
        if not self.clockwise(polygon_): # Qt.WindingFill 与逆时针的多边形不兼容
            polygon_.reverse()
            prectl_.reverse()
            nexctl_.reverse()
            prectl_, nexctl_ = nexctl_, prectl_
            reversed = True
        polygon = QPolygonF(polygon_)
        prectl = QPolygonF(prectl_)
        nexctl = QPolygonF(nexctl_)

        subpath_list = []
        for i in range(len(polygon)):
            tpath = QPainterPath()
            if i == 0:
                pass
            else:
                tpath.moveTo(polygon.value(i - 1) * self.scale)
                tpath.cubicTo(nexctl.value(i - 1) * self.scale, prectl.value(i) * self.scale, polygon.value(i) * self.scale)
                subpath_list.append(tpath)
        tpath = QPainterPath()
        tpath.moveTo(polygon.value(len(nexctl) - 1) * self.scale)
        tpath.cubicTo(nexctl.value(len(nexctl) - 1) * self.scale, prectl.value(0) * self.scale, polygon.value(0) * self.scale)
        subpath_list.append(tpath)

        self.subpath_list = subpath_list

    def ctlPoints(self):
        focusedPoint = None
        ctlPoints = []
        if self.focusedPointIndex != -1:

            index = self.focusedPointIndex
            focusedPoint = self.polygon.value(index) * self.scale
            if self.prectl.value(index) != focusedPoint:
                ctlPoints.append(self.prectl.value(index) * self.scale)
            if self.nexctl.value(index) != focusedPoint:
                ctlPoints.append(self.nexctl.value(index) * self.scale)

        return focusedPoint, ctlPoints

    # 近邻标注：找点在label里的位置
    def CheckPointNum(self,p):
       for  i,qpoint in enumerate(self.polygon):
            if qpoint == p:
                return i
       return None

    def hoverEnterEvent(self, event: 'QGraphicsSceneHoverEvent') -> None:
        if not self.allowInteract:
            return
        super(PolygonCurveLabel, self).hoverEnterEvent(event)

    def hoverMoveEvent(self, event: 'QGraphicsSceneHoverEvent') -> None:
        if not self.allowInteract:
            return
        super(PolygonCurveLabel, self).hoverMoveEvent(event)
        if self.creating:

            self.prepareGeometryChange()
            self.hoverPointIndex = None
            for i in range(len(self.polygon) - 1):
                t_point = self.polygon.value(i) * self.scale
                t_dist = (event.pos().x() - t_point.x()) ** 2 + (event.pos().y() - t_point.y()) ** 2
                if self.hoverPointIndex == i:
                    diameter = self.h_diameter
                else:
                    diameter = self.diameter
                if t_dist <= (diameter / 2) ** 2:
                    self.hoverPointIndex = i
                    break
            while len(self.polygon) > self.pointNum:
                # print('pop ', len(self.polygon) - 1)
                self.polygon.remove(len(self.polygon) - 1)
                self.prectl.remove(len(self.prectl) - 1)
                self.nexctl.remove(len(self.nexctl) - 1)

            # hover到初始点的时候不用增加新点
            if self.hoverPointIndex != 0 or len(self.polygon) == 0:
                newPoint = self.pointNormalized(QPointF(event.pos()) / self.scale)
                self.polygon.append(newPoint)
                self.prectl.append(newPoint)
                self.nexctl.append(newPoint)

            self.update()
        # elif self.focused and self.allowMove:
        elif self.isSelected() and self.allowMove:
            # self.initCursor()
            if self.modifing == True and self.modified_num != 0:
                while len(self.modified_plg) > self.modified_num:
                    self.modified_plg.pop()
                    self.modified_pre.pop()
                    self.modified_nxt.pop()
                if self.hoverPointIndex is None:
                    newPoint = self.pointNormalized(QPointF(event.pos()) / self.scale)
                    self.modified_plg.append(newPoint)
                    self.modified_pre.append(newPoint)
                    self.modified_nxt.append(newPoint)
                else:
                    self.modified_plg.append(self.polygon.value(self.hoverPointIndex))
                    self.modified_pre.append(self.polygon.value(self.hoverPointIndex))
                    self.modified_nxt.append(self.polygon.value(self.hoverPointIndex))
            # 如果鼠标悬停于边缘，则暂时按扩展边缘点的鼠标手势，否则为整体移动的手势

            polygon_, prectl_, nexctl_ = [], [], []
            for i in range(len(self.polygon)):
                polygon_.append(self.polygon.value(i))
                prectl_.append(self.prectl.value(i))
                nexctl_.append(self.nexctl.value(i))

            reversed = False
            path = QPainterPath()
            if not self.clockwise(polygon_): # Qt.WindingFill 与逆时针的多边形不兼容
                polygon_.reverse()
                prectl_.reverse()
                nexctl_.reverse()
                prectl_, nexctl_ = nexctl_, prectl_
                reversed = True
            polygon = QPolygonF(polygon_)
            prectl = QPolygonF(prectl_)
            nexctl = QPolygonF(nexctl_)

            # subpath_list = []
            # for i in range(len(polygon)):
            #     tpath = QPainterPath()
            #     if i == 0:
            #         pass
            #     else:
            #         tpath.moveTo(polygon.value(i - 1) * self.scale)
            #         tpath.cubicTo(nexctl.value(i - 1) * self.scale, prectl.value(i) * self.scale, polygon.value(i) * self.scale)
            #         subpath_list.append(tpath)
            # tpath = QPainterPath()
            # tpath.moveTo(polygon.value(len(nexctl) - 1) * self.scale)
            # tpath.cubicTo(nexctl.value(len(nexctl) - 1) * self.scale, prectl.value(0) * self.scale, polygon.value(0) * self.scale)
            # subpath_list.append(tpath)

            ## 二分近似查找鼠标点击边缘处的坐标
            for i, path in enumerate(self.subpath_list):
                t, find = self.findNearPoint(path, event.pos())
                if find == True:
                    pixmap = QPixmap(":/resources/添加节点.png")  # pixmap 是 QPixmap()的实例化，QPixmap()类用于图片的显示
                    new_pixmap = pixmap.scaled(32,32)  # scaled方法返回自定义尺寸的副本
                    cursor=QCursor(new_pixmap,0,0)
                    if self.isSelected():
                        self.arced=True
                    break
            else:
                cursor = Qt.SizeAllCursor
                self.arced=False
            flag = False
            for i in range(len(self.polygon)):
                t_point = self.polygon.value(i) * self.scale
                t_dist = (event.pos().x() - t_point.x()) ** 2 + (event.pos().y() - t_point.y()) ** 2
                if self.focusedPointIndex == i:
                    diameter = self.s_diameter
                elif self.hoverPointIndex == i:
                    diameter = self.h_diameter
                else:
                    diameter = self.diameter
                if t_dist <= (diameter / 2 + 2) ** 2:
                    self.hoverPointIndex = i
                    flag = True
                    if self.addCtl:
                        pixmap = QPixmap(":/resources/添加控制点.png")  # pixmap 是 QPixmap()的实例化，QPixmap()类用于图片的显示
                        new_pixmap = pixmap.scaled(32,32)  # scaled方法返回自定义尺寸的副本
                        cursor=QCursor(new_pixmap,0,0)
                    else:
                        if i == 0:
                            a = self.polygon.value(len(self.polygon) - 1)
                            b = self.polygon.value(i)
                            c = self.polygon.value(i + 1)
                        elif i == len(self.polygon) - 1:
                            a = self.polygon.value(i - 1)
                            b = self.polygon.value(i)
                            c = self.polygon.value(0)
                        else:
                            a = self.polygon.value(i - 1)
                            b = self.polygon.value(i)
                            c = self.polygon.value(i + 1)
                        cursor = self.angle2Cursor(a, b, c)
                    break

            if not flag:
                self.hoverPointIndex = None

            self.setCursor(cursor)
            self.update()

    def angle2Cursor(self, A, B, C):

        def clockwise_angle(v1, v2):
            x1,y1 = v1
            x2,y2 = v2
            dot = x1*x2+y1*y2
            det = x1*y2-y1*x2
            theta = np.arctan2(det, dot)
            theta = theta if theta>0 else 2*np.pi+theta
            return np.degrees(theta)

        a = np.array((A.x(), A.y()))
        b = np.array((B.x(), B.y()))
        c = np.array((C.x(), C.y()))
        avec = a - b
        bvec = np.array((100, 0))
        cvec = c - b
        a1 = clockwise_angle(avec, bvec)
        a2 = clockwise_angle(cvec, bvec)
        a = (a1 + a2) / 2 % 180
        if -22.5 < a <= 22.5 or 157.5 < a <= 180:
            cursor = Qt.SizeHorCursor
        elif 22.5 < a <= 67.5:
            cursor = Qt.SizeBDiagCursor
        elif 67.5 < a <= 112.5:
            cursor = Qt.SizeVerCursor
        elif 112.5 < a <= 157.5:
            cursor = Qt.SizeFDiagCursor
        return cursor


    def hoverLeaveEvent(self, event: 'QGraphicsSceneHoverEvent') -> None:
        if not self.allowInteract:
            return
        super(PolygonCurveLabel, self).hoverLeaveEvent(event)
        # self.setCursor(Qt.OpenHandCursor)
        self.unsetCursor()
        self.hoverPointIndex = None
        self.update()
        # print("hover leave")
        pass

    def selectedPointIndex(self, x, y):
        # 判断鼠标点击的具体位置
        dist_index = -1
        min_dist = 10000000
        for i in range(len(self.polygon)):
            t_point = self.polygon.value(i) * self.scale
            t_dist = (x - t_point.x()) ** 2 + (y - t_point.y()) ** 2
            if i == self.hoverPointIndex:
                diameter = self.h_diameter
            elif i == self.focusedPointIndex:
                diameter = self.s_diameter
            else:
                diameter = self.diameter
            if t_dist <= (diameter / 2 + 2) ** 2 and t_dist < min_dist:
                dist_index = i
                min_dist = t_dist
        return dist_index

    def mousePressEvent(self, event) -> None:
        if not self.allowInteract:
            return
        # self.focused = True
        # self.setSelected(True)
        self.selectedItem.emit(self)
        # super().mousePressEvent(event)
        if self.creating:
            if event.buttons() & Qt.RightButton:
                self.rightClicked = True
            else:
                self.rightClicked = False
            if self.rightClicked and self.quicked == False:
                self.Die = True
                self.hide()
                self.setInteract(False)
                self.creating = False
                self.drawText = True
                self.update()
                self.creatingFinish.emit(self)
            elif self.rightClicked and self.quicked == True:
                pass
            # elif self.lastPoint != None:
            elif self.hoverPointIndex == 0:
                if len(self.polygon) < 2:
                    self.Die = True
                    self.hide()
                    self.setInteract(False)
                else:
                    self.creatingSuccess.emit(self.type, self.labelClass) # 多边形标注成功

                self.creating = False
                self.drawText = True
                self.update()
                self.creatingFinish.emit(self)
                self.focusedPointIndex = 0
                self.allowMove = True
                # event.accept()
            elif self.rightClicked==False and self.quicking==False:
                self.lastPoint = None
                self.pointNum += 1
                self.focusedPointIndex = self.pointNum - 1
            elif self.quicking==True:
                self.quicking=False
            else:
                # self.polygon.remove(len(self.polygon) - 1)
                # self.polygon.append(event.pos() / self.scale)
                self.lastPoint = None
                self.pointNum += 1
                self.focusedPointIndex = self.pointNum - 1
        else:
            self.moveSrcPoints = self.getPoints()   # 记录修改之前状态

            tPos = event.pos()
            x = tPos.x()
            y = tPos.y()

            if self.focusedPointIndex != -1:    # 初始化选中的锚点
                index = self.focusedPointIndex
                t_point1, t_point2, t_point3 = self.prectl.value(index) * self.scale, self.nexctl.value(index) * self.scale, self.polygon.value(index) * self.scale
                t_dist1 = (event.pos().x() - t_point1.x()) ** 2 + (event.pos().y() - t_point1.y()) ** 2
                t_dist2 = (event.pos().x() - t_point2.x()) ** 2 + (event.pos().y() - t_point2.y()) ** 2
                t_dist3 = (event.pos().x() - t_point3.x()) ** 2 + (event.pos().y() - t_point3.y()) ** 2
                if t_dist1 > (self.diameter / 2 + 2) ** 2 and t_dist2 > (self.diameter / 2 + 2) ** 2 and self.modifing == False:
                # if t_dist1 > (self.diameter / 2) ** 2 and t_dist2 > (self.diameter / 2) ** 2 and self.modifing == False:
                    self.focusedPointIndex = -1
                    self.ctlPointIndex = -1
            if event.buttons() & Qt.LeftButton or event.buttons() & Qt.RightButton:
                dist_index = self.selectedPointIndex(x, y)
                if dist_index != -1:    # 点击了锚点
                    self.selected_index = dist_index
                    self.setCursor(Qt.CrossCursor)

                    for i in range(len(self.polygon)):
                        t_point = self.polygon.value(i) * self.scale
                        t_dist = (event.pos().x() - t_point.x()) ** 2 + (event.pos().y() - t_point.y()) ** 2
                        if t_dist <= (self.diameter / 2 + 2) ** 2:
                            self.focusedPointIndex = i
                            break
                    if self.modifing == True:
                        if len(self.modified_plg) == 0:    # 增量修改入口
                            self.modified_plg.append(self.polygon.value(i))
                            self.modified_pre.append(self.polygon.value(i))
                            self.modified_nxt.append(self.polygon.value(i))
                            self.modified_num += 1
                            self.drawText = False
                        else:                               # 增量修改结束
                            begin = self.modified_plg[0]
                            end = self.modified_plg[-1]
                            t_plg, n_plg = [], []
                            t_pre, n_pre = [], []
                            t_nxt, n_nxt = [], []
                            for i in range(len(self.polygon)):
                                t_plg.append(self.polygon.value(i))
                                t_pre.append(self.prectl.value(i))
                                t_nxt.append(self.nexctl.value(i))
                                if self.polygon.value(i) == begin:
                                    begin_i = i
                                if self.polygon.value(i) == end:
                                    end_i = i
                            right = True if (end_i - begin_i) % len(t_plg) <= len(t_plg) - (end_i - begin_i) % len(t_plg) else False
                            if not right:
                                begin_i, end_i = end_i, begin_i
                                self.modified_plg.reverse()
                                self.modified_pre.reverse()
                                self.modified_nxt.reverse()
                            i = 0
                            if begin_i < end_i:
                                n_plg += t_plg[0:begin_i]
                                n_plg += self.modified_plg
                                n_pre += t_pre[0:begin_i]
                                n_pre += self.modified_pre
                                n_nxt += t_nxt[0:begin_i]
                                n_nxt += self.modified_nxt
                                if end_i + 1 < len(t_plg):
                                    n_plg += t_plg[end_i + 1:]
                                    n_pre += t_pre[end_i + 1:]
                                    n_nxt += t_nxt[end_i + 1:]
                            elif begin_i > end_i:
                                n_plg += self.modified_plg
                                n_plg += t_plg[end_i + 1:begin_i]
                                n_pre += self.modified_pre
                                n_pre += t_pre[end_i + 1:begin_i]
                                n_nxt += self.modified_nxt
                                n_nxt += t_nxt[end_i + 1:begin_i]
                            if n_plg:
                                self.polygon = QPolygonF(n_plg)
                                self.prectl = QPolygonF(n_pre)
                                self.nexctl = QPolygonF(n_nxt)
                            self.clearModify()
                            self.modifing = False
                            self.drawText = True
                            self.update()
                elif self.arced and self.isSelected():
                    polygon_, prectl_, nexctl_ = [], [], []
                    for i in range(len(self.polygon)):
                        polygon_.append(self.polygon.value(i))
                        prectl_.append(self.prectl.value(i))
                        nexctl_.append(self.nexctl.value(i))
                    reversed = False
                    path = QPainterPath()
                    if not self.clockwise(polygon_):  # Qt.WindingFill 与逆时针的多边形不兼容
                        polygon_.reverse()
                        prectl_.reverse()
                        nexctl_.reverse()
                        prectl_, nexctl_ = nexctl_, prectl_
                        reversed = True
                    polygon = QPolygonF(polygon_)
                    prectl = QPolygonF(prectl_)
                    nexctl = QPolygonF(nexctl_)
                    for i, path in enumerate(self.subpath_list):
                        t, find = self.findNearPoint(path, tPos)
                        # print(i)  # i为鼠标前面的point的index
                        if find == True:
                            #self.moveSrcPoints = self.getPoints()
                            if reversed:
                                polygon_.reverse()
                                prectl_.reverse()
                                nexctl_.reverse()
                                prectl_, nexctl_ = nexctl_, prectl_
                            self.polygon = QPolygonF(polygon_)
                            self.prectl = QPolygonF(prectl_)
                            self.nexctl = QPolygonF(nexctl_)
                            self.pressed = True
                            if not reversed:
                                self.focusedPointIndex=i
                            else:
                                self.focusedPointIndex =(len(self.polygon) - i - 2)%self.pointNum
                            self.ctlPointIndex = 1
                    self.update()
                elif self.modifing and self.modified_num != 0:     # 选中会掩盖增量修改
                    self.modified_num += 1
                elif  self.focusedPointIndex != -1:  # 点击了控制点
                    if t_dist1 <= (self.diameter / 2 + 2) ** 2:
                        self.ctlPointIndex = 0
                    elif t_dist2 <= (self.diameter / 2 + 2) ** 2:
                        self.ctlPointIndex = 1
                else:   # 点击内部点
                    self.moving_all = True
                    self.selected_index = None

    def clearModify(self):
        self.modified_plg.clear()
        self.modified_pre.clear()
        self.modified_nxt.clear()
        self.modified_num = 0


    def findNearPoint(self, path, pos):
        # 二分近似查找鼠标点击边缘处的坐标
        x, y = 0, 1
        max_d = 65535
        count = 0
        find = True
        t = 0
        while max_d > self.penWidth:
            # 二分查找次数设置上限，否则会卡死
            if count >= 10:
                find = False
                break
            m = (x + y) / 2
            m1 = (x + m) / 2
            m2 = (y + m) / 2

            t1 = path.pointAtPercent(m1)
            t2 = path.pointAtPercent(m2)

            l1 = euclideanDistance(t1, pos)
            l2 = euclideanDistance(t2, pos)

            if l1 < l2:
                y = m
                t = m
            else:
                x = m
                t = m
            max_d = max(l1, l2)
            count += 1
        return t, find


    def mouseDoubleClickEvent(self, event: 'QGraphicsSceneMouseEvent') -> None:
        if not self.allowInteract:
            return
        if self.creating:
            if len(self.polygon) < 5:
                self.Die = True
                self.hide()
                self.setInteract(False)
            else:
                self.polygon.remove(len(self.polygon) - 1)
                self.prectl.remove(len(self.prectl) - 1)
                self.nexctl.remove(len(self.nexctl) - 1)
                self.polygon.remove(len(self.polygon) - 1)
                self.prectl.remove(len(self.prectl) - 1)
                self.nexctl.remove(len(self.nexctl) - 1)
                self.creatingSuccess.emit(self.type, self.labelClass) # 多边形标注完成

            self.pointNum = self.pointNum - 1#对双击生成多边形快速标记

            self.creating = False
            self.drawText = True
            self.allowMove = True
            self.update()
            self.creatingFinish.emit(self)
        else:
            # 双击增加点
            localPos = event.pos()
            polygon_, prectl_, nexctl_ = [], [], []
            for i in range(len(self.polygon)):
                polygon_.append(self.polygon.value(i))
                prectl_.append(self.prectl.value(i))
                nexctl_.append(self.nexctl.value(i))

            reversed = False
            path = QPainterPath()
            if not self.clockwise(polygon_): # Qt.WindingFill 与逆时针的多边形不兼容
                polygon_.reverse()
                prectl_.reverse()
                nexctl_.reverse()
                prectl_, nexctl_ = nexctl_, prectl_
                reversed = True
            polygon = QPolygonF(polygon_)
            prectl = QPolygonF(prectl_)
            nexctl = QPolygonF(nexctl_)

            # path.addPath(self.bezierPath(polygon, prectl, nexctl, True))
            # path = self.painterPath

            # subpath_list = []
            # for i in range(len(polygon)):
            #     tpath = QPainterPath()
            #     if i == 0:
            #         pass
            #     else:
            #         tpath.moveTo(polygon.value(i - 1) * self.scale)
            #         tpath.cubicTo(nexctl.value(i - 1) * self.scale, prectl.value(i) * self.scale, polygon.value(i) * self.scale)
            #         subpath_list.append(tpath)
            # tpath = QPainterPath()
            # tpath.moveTo(polygon.value(len(nexctl) - 1) * self.scale)
            # tpath.cubicTo(nexctl.value(len(nexctl) - 1) * self.scale, prectl.value(0) * self.scale, polygon.value(0) * self.scale)
            # subpath_list.append(tpath)

            # print(path.pointAtPercent(0))
            # print(path.pointAtPercent(1))

            for i, path in enumerate(self.subpath_list):
                t, find = self.findNearPoint(path, localPos)

                if find == True:
                    self.moveSrcPoints = self.getPoints()
                    # length = 0
                    # for i, tpath in enumerate(subpath_list):
                    #     length += tpath.length()
                    #     percent = length / path.length()
                    #     if percent > t:
                    #         break
                    polygon_.insert(i + 1, localPos / self.scale)
                    prectl_.insert(i + 1, localPos / self.scale)
                    nexctl_.insert(i + 1, localPos / self.scale)
                    if reversed:
                        polygon_.reverse()
                        prectl_.reverse()
                        nexctl_.reverse()
                        prectl_, nexctl_ = nexctl_, prectl_

                    self.polygon = QPolygonF(polygon_)
                    self.prectl = QPolygonF(prectl_)
                    self.nexctl = QPolygonF(nexctl_)
                    if not reversed:
                        self.focusedPointIndex = i + 1
                    else:
                        self.focusedPointIndex = len(self.polygon) - i - 2
                    self.doubleClicked = True
                    self.update()
                    self.moveDstPoints = self.getPoints()
                    self.posChanged.emit(self.moveSrcPoints, self.moveDstPoints)
                    self.moveSrcPoints = None
                    print('double click')
                    self.pointNum=self.pointNum+1
                    break

    def mouseMoveEvent(self, event) -> None:
        if not self.allowInteract:
            return
        self.moved = True
        # event.accept()
        # 创建标注或点
        if self.creating or self.addCtl or self.doubleClicked:
            targetIndex = len(self.polygon) - 1 if self.creating else self.focusedPointIndex
            self.nexctl.remove(targetIndex)
            tPoint = event.pos()
            anchorPoint = self.polygon.value(targetIndex) * self.scale
            t_dist = (tPoint.x() - anchorPoint.x()) ** 2 + (tPoint.y() - anchorPoint.y()) ** 2
            if t_dist <= (self.s_diameter / 2 + 2) ** 2:
                tPoint = anchorPoint
            self.nexctl.insert(targetIndex, tPoint / self.scale)
            ox = 2 * self.polygon.value(targetIndex).x() * self.scale - event.pos().x()
            oy = 2 * self.polygon.value(targetIndex).y() * self.scale - event.pos().y()
            othersidePoint = QPointF(ox, oy)
            self.prectl.remove(targetIndex)
            tPoint = othersidePoint
            anchorPoint = self.polygon.value(targetIndex) * self.scale
            t_dist = (tPoint.x() - anchorPoint.x()) ** 2 + (tPoint.y() - anchorPoint.y()) ** 2
            if t_dist <= (self.s_diameter / 2 + 2) ** 2:
                tPoint = anchorPoint
            self.prectl.insert(targetIndex, tPoint / self.scale)
            self.update()
        # 增量添加点
        elif self.modifing and self.modified_num != 0:
            targetIndex = self.modified_num - 1
            self.modified_nxt.pop(targetIndex)
            tPoint = event.pos()
            anchorPoint = self.modified_plg[targetIndex] * self.scale
            t_dist = (tPoint.x() - anchorPoint.x()) ** 2 + (tPoint.y() - anchorPoint.y()) ** 2
            if t_dist <= (self.s_diameter / 2 + 2) ** 2:
                tPoint = anchorPoint
            self.modified_nxt.insert(targetIndex, tPoint / self.scale)
            ox = 2 * self.modified_plg[targetIndex].x() * self.scale - event.pos().x()
            oy = 2 * self.modified_plg[targetIndex].y() * self.scale - event.pos().y()
            othersidePoint = QPointF(ox, oy)
            self.modified_pre.pop(targetIndex)
            tPoint = othersidePoint
            anchorPoint = self.modified_plg[targetIndex] * self.scale
            t_dist = (tPoint.x() - anchorPoint.x()) ** 2 + (tPoint.y() - anchorPoint.y()) ** 2
            if t_dist <= (self.s_diameter / 2 + 2) ** 2:
                tPoint = anchorPoint
            self.modified_pre.insert(targetIndex, tPoint / self.scale)
            self.update()
        # 拖动点的位置
        elif self.selected_index != None and self.ctlPointIndex == -1:
            oldPoint = self.polygon.value(self.selected_index)
            oldPre = self.prectl.value(self.selected_index)
            oldNex = self.nexctl.value(self.selected_index)

            self.polygon.remove(self.selected_index)
            self.prectl.remove(self.selected_index)
            self.nexctl.remove(self.selected_index)

            newPoint = self.pointNormalized(event.pos() / self.scale)
            oPos = newPoint - oldPoint
            newPre = oldPre + oPos
            newNex = oldNex + oPos

            self.polygon.insert(self.selected_index, newPoint)
            self.prectl.insert(self.selected_index, newPre)
            self.nexctl.insert(self.selected_index, newNex)
            self.drawText = False
            self.prepareGeometryChange()
            self.update()
            # 拖动控制点
        elif self.ctlPointIndex != -1:
            index = self.focusedPointIndex
            if self.ctlPointIndex == 0:
                self.prectl.remove(index)
                tPoint = event.pos()
                anchorPoint = self.polygon.value(index) * self.scale
                t_dist = (tPoint.x() - anchorPoint.x()) ** 2 + (tPoint.y() - anchorPoint.y()) ** 2
                if t_dist <= (self.s_diameter / 2 + 2) ** 2:
                    tPoint = anchorPoint
                self.prectl.insert(index, tPoint / self.scale)
            elif self.ctlPointIndex == 1:
                self.nexctl.remove(index)
                tPoint = event.pos()
                anchorPoint = self.polygon.value(index) * self.scale
                t_dist = (tPoint.x() - anchorPoint.x()) ** 2 + (tPoint.y() - anchorPoint.y()) ** 2
                if t_dist <= (self.s_diameter / 2 + 2) ** 2:
                    tPoint = anchorPoint
                self.nexctl.insert(index, tPoint / self.scale)
            self.update()
        elif self.pressed:
            index = self.focusedPointIndex
            self.nexctl.remove(index)
            tPoint = event.pos()
            anchorPoint = self.polygon.value(index) * self.scale
            t_dist = (tPoint.x() - anchorPoint.x()) ** 2 + (tPoint.y() - anchorPoint.y()) ** 2
            if t_dist <= (self.s_diameter / 2 + 2) ** 2:
                tPoint = anchorPoint
            self.nexctl.insert(index, tPoint / self.scale)
            self.update()
            # 拖动整体
        elif self.moving_all:
            self.polygon.translate((event.pos() - event.lastPos()) / self.scale)
            self.prectl.translate((event.pos() - event.lastPos()) / self.scale)
            self.nexctl.translate((event.pos() - event.lastPos()) / self.scale)
            self.contourNormalized()
            self.drawText = False
            self.prepareGeometryChange()
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if not self.allowInteract:
            return
        # if not self.creating and self.selected_index != None:
        #     self.selected_index = None
        #     self.drawText = True
        #     self.update()

        if self.moving_all:
            self.moving_all = False
            self.drawText = True
            self.update()
        if self.moveSrcPoints:
            if self.moved or self.doubleClicked:
                self.moveDstPoints = self.getPoints()
                self.posChanged.emit(self.moveSrcPoints, self.moveDstPoints)
        self.moveSrcPoints = None
        self.moveDstPoints = None
        self.doubleClicked = False
        self.moved = False
        self.ctlPointIndex = -1
        self.pressed=False
        #A修改
        self.centers = self.getAllCenters()
        self.update()

    def contourNormalized(self):
        polygon, prectl, nexctl = [], [], []
        for i in range(len(self.polygon)):
            polygon.append(self.polygon.value(i))
        ox, oy = self.posOffset(polygon)
        self.polygon.translate(ox, oy)
        self.prectl.translate(ox, oy)
        self.nexctl.translate(ox, oy)

    '''
    description: 删除localpos位置的关键点及控制点
    param {*} self
    param {*} localPos
    return {*}
    '''
    def deleteKeyPoint(self, localPos):
        if len(self.polygon) <=2:
            return
        pointIndex = self.selectedPointIndex(localPos.x(), localPos.y())
        self.polygon.remove(pointIndex)
        self.prectl.remove(pointIndex)
        self.nexctl.remove(pointIndex)
        self.update()


    def exportPixmap(self):
        t_painter = QPainter()
        pixmap = QPixmap(int(self.cRect.width()), int(self.cRect.height()))
        pixmap.fill(QColor(0,0,0))
        t_painter.begin(pixmap)
        t_painter.setPen(Qt.NoPen)
        t_painter.setBrush(self.selectBrush)
        # t_painter.setCompositionMode(QPainter.CompositionMode_Source)
        t_painter.setRenderHint(QPainter.Antialiasing)
        t_painter.drawPath(self.bezierPath(self.polygon, self.prectl, self.nexctl, True))
        t_painter.end()
        return pixmap


    def exportMask(self):
        pixmap = self.exportPixmap()
        mask = lblPixmapToNmp(pixmap, gray=True)

        # mask = np.zeros((int(self.cRect.width()), int(self.cRect.height())), dtype=np.uint8)
        # where = np.where(nmp != (0,0,0))
        # mask[where] = 255
        return mask


    def getExport(self):
        dict = super(PolygonCurveLabel, self).getExport()
        points1 = []
        for i in range(len(self.polygon)):
            points1.append((self.polygon.value(i).x(), self.polygon.value(i).y()))
        points2 = []
        for i in range(len(self.prectl)):
            points2.append((self.prectl.value(i).x(), self.prectl.value(i).y()))
        points3 = []
        for i in range(len(self.nexctl)):
            points3.append((self.nexctl.value(i).x(), self.nexctl.value(i).y()))
        dict["point_list"] = [points1, points2, points3]

        return dict

    def getPoints(self):
        points1 = []
        for i in range(len(self.polygon)):
            points1.append(self.polygon.value(i))
        points2 = []
        for i in range(len(self.prectl)):
            points2.append(self.prectl.value(i))
        points3 = []
        for i in range(len(self.nexctl)):
            points3.append(self.nexctl.value(i))
        return [points1, points2, points3]

    def setPoints(self, points):
        points1, points2, points3 = points
        self.polygon = QPolygonF(points1)
        self.prectl = QPolygonF(points2)
        self.nexctl = QPolygonF(points3)
        self.update()


class LineLabel(Label):

    def __init__(self, polygon, pRect, cRect, frontColor, backColor, type, operator, confidence):
        super(LineLabel, self).__init__(pRect, cRect, frontColor, backColor, type, operator, confidence)
        self.polygon = polygon

        self.basePoint = self.polygon.value(0)
        self.lastPoint = self.polygon.value(0)
        self.selected_index = None
        self.moving_all = False

        if self.polygon.count() <= 1:
            self.creating = True
            # self.lastPoint = None
        self.labelClass = "Line"
        self.updateColor()

    def shape(self):
        """
        shape可以比boundingrect更为复杂
        @return:
        """
        temp = QPainterPath()
        temp.setFillRule(Qt.WindingFill)
        if self.creating:
            temp.addRect(self.paintRect())
        else:
            temp_point_list = []
            for i in range(len(self.polygon)):
                temp_point_list.append(self.polygon.value(i) * self.scale)

            for i in range(len(self.polygon)):
                if i == self.hoverPointIndex:
                    diameter = self.h_diameter
                else:
                    diameter = self.diameter
                temp.addEllipse(self.polygon.value(i) * self.scale, diameter / 2, diameter / 2)
            if not self.clockwise(temp_point_list):
                temp_point_list.reverse()
            temp.addPolygon(QPolygonF(temp_point_list))

            temp.addRect(self.textZone()[0])

        return temp

    def clockwise(self, points_list):
        n = len(points_list)
        if n < 3:
            return 0.0
        area = 0
        for i in range(n):
            x = points_list[i].x()
            y = points_list[i].y()
            area += x * points_list[(i + 1) % n].y() - y * points_list[(i + 1) % n].x()
        return True if area > 0 else False

    def textZone(self):
        """
        用于计算信息区域的显示范围
        @return:
        """
        if self.textWidth == None:
            self.textWidth = self.font.pixelSize() * 4
        for i in range(len(self.polygon)):
            if i == 0:
                textPoint = self.polygon.value(i)
            elif textPoint.y() > self.polygon.value(i).y():
                textPoint = self.polygon.value(i)
        rect1, rect2, rect3, rect4 = self.textRect(textPoint.x(), textPoint.y())
        return rect1, rect2, rect3, rect4

    def paint(self, painter, option, widget):
        painter.setPen(self.selectPen)
        painter.setBrush(self.selectBrush)
        painter.setRenderHint(QPainter.Antialiasing)

        temp_point_list = []
        for i in range(len(self.polygon)):
            temp_point_list.append(self.polygon.value(i) * self.scale)

        if self.creating:
            painter.drawPolyline(QPolygonF(temp_point_list))
            painter.setPen(Qt.NoPen)
        painter.drawPolyline(QPolygonF(temp_point_list))

        # 如果被选中就绘制每个点的圆圈
        # if self.focused:
        if self.isSelected():
            painter.setPen(Qt.NoPen)
            painter.setBrush(self.labelBrush)

            count = 0
            for i, point in enumerate(temp_point_list):

                if count == 0 and self.creating:
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(QBrush(QColor(255, 255, 255)))
                else:
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(self.labelBrush)
                if i == self.hoverPointIndex:
                    diameter = self.h_diameter
                else:
                    diameter = self.diameter
                painter.drawEllipse(point, diameter / 2, diameter / 2)
                count += 1
            t_pen = QPen(QColor(255, 255, 255))
            t_pen.setWidth(2)
            t_pen.setStyle(Qt.DotLine)
            painter.setPen(t_pen)
            painter.setBrush(Qt.NoBrush)

            painter.drawPolyline(QPolygonF(temp_point_list))

        if self.drawText:
            painter.setPen(self.textPen)
            painter.setFont(self.font)
            self.textWidth = painter.fontMetrics().boundingRect(self.text()).width()

            rect1, rect2, rect3, rect4 = self.textZone()
            painter.setPen(self.labelPen1)
            painter.setBrush(self.labelBrush1)
            painter.drawRect(rect1)

            painter.setPen(self.labelPen2)
            painter.setBrush(self.labelBrush2)
            painter.drawRect(rect2)

            painter.setPen(self.labelPen1)
            painter.setBrush(self.labelBrush1)
            painter.drawRect(rect3)

            painter.setPen(self.textPen)
            painter.setFont(self.font)
            painter.drawText(rect4, Qt.AlignCenter, self.text())

    def hoverEnterEvent(self, event: 'QGraphicsSceneHoverEvent') -> None:
        if not self.allowInteract:
            return
        super(LineLabel, self).hoverEnterEvent(event)

    def hoverMoveEvent(self, event: 'QGraphicsSceneHoverEvent') -> None:
        if not self.allowInteract:
            return
        super(LineLabel, self).hoverMoveEvent(event)
        if self.creating:
            if self.lastPoint != None:
                self.polygon.remove(len(self.polygon) - 1)
            self.lastPoint = event.pos()
            newPoint = QPointF(event.pos()) / self.scale
            self.polygon.append(self.pointNormalized(newPoint))
            self.prepareGeometryChange()
            flag = False
            for i in range(len(self.polygon) - 1):
                t_point = self.polygon.value(i) * self.scale
                t_dist = (event.pos().x() - t_point.x()) ** 2 + (event.pos().y() - t_point.y()) ** 2
                if i == self.hoverPointIndex:
                    diameter = self.h_diameter
                else:
                    diameter = self.diameter
                if t_dist <= (diameter / 2) ** 2:
                    self.hoverPointIndex = i
                    flag = True
                    break
            if not flag:
                self.hoverPointIndex = None
            self.update()
        # elif self.focused and self.allowMove:
        elif self.isSelected() and self.allowMove:
            # self.initCursor()
            flag = False
            cursor = Qt.SizeAllCursor
            for i in range(len(self.polygon)):
                t_point = self.polygon.value(i) * self.scale
                t_dist = (event.pos().x() - t_point.x()) ** 2 + (event.pos().y() - t_point.y()) ** 2
                if i == self.hoverPointIndex:
                    diameter = self.h_diameter
                else:
                    diameter = self.diameter
                if t_dist <= (diameter / 2) ** 2:
                    self.hoverPointIndex = i
                    if i == 0:
                        a = self.polygon.value(len(self.polygon) - 1)
                        b = self.polygon.value(i)
                        c = self.polygon.value(i + 1)
                    elif i == len(self.polygon) - 1:
                        a = self.polygon.value(i - 1)
                        b = self.polygon.value(i)
                        c = self.polygon.value(0)
                    else:
                        a = self.polygon.value(i - 1)
                        b = self.polygon.value(i)
                        c = self.polygon.value(i + 1)
                    cursor = self.angle2Cursor(a, b, c)
                    flag = True
            if not flag:
                self.hoverPointIndex = None
            self.setCursor(cursor)
            self.update()

    def angle2Cursor(self, A, B, C):

        def clockwise_angle(v1, v2):
            x1,y1 = v1
            x2,y2 = v2
            dot = x1*x2+y1*y2
            det = x1*y2-y1*x2
            theta = np.arctan2(det, dot)
            theta = theta if theta>0 else 2*np.pi+theta
            return np.degrees(theta)

        a = np.array((A.x(), A.y()))
        b = np.array((B.x(), B.y()))
        c = np.array((C.x(), C.y()))
        avec = a - b
        bvec = np.array((100, 0))
        cvec = c - b
        a1 = clockwise_angle(avec, bvec)
        a2 = clockwise_angle(cvec, bvec)
        a = (a1 + a2) / 2 % 180
        if -22.5 < a <= 22.5 or 157.5 < a <= 180:
            cursor = Qt.SizeHorCursor
        elif 22.5 < a <= 67.5:
            cursor = Qt.SizeBDiagCursor
        elif 67.5 < a <= 112.5:
            cursor = Qt.SizeVerCursor
        elif 112.5 < a <= 157.5:
            cursor = Qt.SizeFDiagCursor
        return cursor


    def hoverLeaveEvent(self, event: 'QGraphicsSceneHoverEvent') -> None:
        if not self.allowInteract:
            return
        super(LineLabel, self).hoverLeaveEvent(event)
        # self.setCursor(Qt.OpenHandCursor)
        self.unsetCursor()
        self.hoverPointIndex = None
        self.update()
        # print("hover leave")
        pass

    def selectedPointIndex(self, x, y):
        # 判断鼠标点击的具体位置
        dist_index = -1
        min_dist = 10000000
        for i in range(len(self.polygon)):
            t_point = self.polygon.value(i) * self.scale
            t_dist = (x - t_point.x()) ** 2 + (y - t_point.y()) ** 2
            if i == self.hoverPointIndex:
                diameter = self.h_diameter
            else:
                diameter = self.diameter
            if t_dist <= (diameter / 2) ** 2 and t_dist < min_dist:
                dist_index = i
                min_dist = t_dist
        return dist_index

    def mousePressEvent(self, event) -> None:
        if not self.allowInteract:
            return
        # self.focused = True
        # self.setSelected(True)
        self.selectedItem.emit(self)
        if self.creating:
            if event.buttons() & Qt.RightButton:
                self.rightClicked = True
            else:
                self.rightClicked = False

            if self.rightClicked:
                self.Die = True
                self.hide()
                self.setInteract(False)
                self.creating = False
                self.drawText = True
                self.update()
                self.creatingFinish.emit(self)
            elif self.lastPoint != None:
                if self.hoverPointIndex == 0:
                    if len(self.polygon) < 3:
                        self.Die = True
                        self.hide()
                        self.setInteract(False)
                    else:
                        self.polygon.remove(len(self.polygon) - 1)
                        self.creatingSuccess.emit(self.type, self.labelClass)
                    self.creating = False
                    self.drawText = True
                    self.update()
                    self.creatingFinish.emit(self)
                    self.allowMove = True

                else:
                    self.polygon.remove(len(self.polygon) - 1)
                    newPoint = event.pos() / self.scale
                    self.polygon.append(self.pointNormalized(newPoint))
                    self.lastPoint = None
        else:
            self.moveSrcPoints = self.getPoints()
        if self.drawText:
            tPos = event.pos()
            x = tPos.x()
            y = tPos.y()

            if event.buttons() & Qt.LeftButton or event.buttons() & Qt.RightButton:
                dist_index = self.selectedPointIndex(x, y)
                if dist_index != -1:
                    self.selected_index = dist_index
                    self.setCursor(Qt.CrossCursor)
                else:
                    self.moving_all = True

    def mouseDoubleClickEvent(self, event: 'QGraphicsSceneMouseEvent') -> None:
        if not self.allowInteract:
            return
        if self.creating:
            if len(self.polygon) < 4:
                self.Die = True
                self.hide()
                self.setInteract(False)
            else:
                self.polygon.remove(len(self.polygon) - 1)
                self.polygon.remove(len(self.polygon) - 1)
                self.creatingSuccess.emit(self.type, "instance")
            self.creating = False
            self.drawText = True
            self.update()
            self.creatingFinish.emit(self)
            self.allowMove = True
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if not self.allowInteract:
            return
        self.moved = True
        if not self.creating and self.selected_index != None:
            self.polygon.remove(self.selected_index)
            newPoint = event.pos() / self.scale
            self.polygon.insert(self.selected_index, self.pointNormalized(newPoint))
            self.drawText = False
            self.prepareGeometryChange()
            self.update()

        elif self.moving_all:
            self.polygon.translate((event.pos() - event.lastPos()) / self.scale)
            self.contourNormalized()
            self.drawText = False
            self.prepareGeometryChange()
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if not self.allowInteract:
            return
        if not self.creating and self.selected_index != None:
            self.selected_index = None
            self.drawText = True
            self.update()

        if self.moving_all:
            self.moving_all = False
            self.drawText = True
            self.update()

        if self.moveSrcPoints and self.moved:
            self.moveDstPoints = self.getPoints()
            self.posChanged.emit(self.moveSrcPoints, self.moveDstPoints)
        self.moved = False
        self.moveSrcPoints = None
        self.moveDstPoints = None

    def contourNormalized(self):
        polygon = []
        for i in range(len(self.polygon)):
            polygon.append(self.polygon.value(i))
        ox, oy = self.posOffset(polygon)
        self.polygon.translate(ox, oy)

    def getExport(self):
        dict = super(LineLabel, self).getExport()
        temp = []
        for i in range(len(self.polygon)):
            temp.append((self.polygon.value(i).x(), self.polygon.value(i).y()))
        dict["point_list"] = temp

        return dict

    def getPoints(self):
        points = []
        for i in range(len(self.polygon)):
            points.append(self.polygon.value(i))
        return points

    def setPoints(self, points):
        # assert len(points) >= 3
        self.polygon = QPolygonF(points)
        self.update()

class PointLabel(Label):
    IsMoving = pyqtSignal()
    MovingDone = pyqtSignal()
    def __init__(self, point, pRect, cRect, frontColor, backColor, type, operator, confidence):
        super(PointLabel, self).__init__(pRect, cRect, frontColor, backColor, type, operator, confidence)
        self.labelClass = "Point"
        self.point = point
        # self.origimg = origimg
        self.diameter /= 2
        self.creating = True


    def shape(self):
        """
        shape可以比boundingrect更为复杂
        @return:
        """
        temp = QPainterPath()
        temp.setFillRule(Qt.WindingFill)
        if self.isSelected():
            temp.addEllipse(self.point * self.scale, self.s_diameter / 2, self.s_diameter / 2)
        elif self.hoverPointIndex == 0:
            temp.addEllipse(self.point * self.scale, self.h_diameter / 2, self.h_diameter / 2)
        else:
            temp.addEllipse(self.point * self.scale, self.diameter / 2, self.diameter / 2)
        if self.drawText:
            temp.addRect(self.textZone()[0])

        return temp

    def textZone(self):
        """
        用于计算信息区域的显示范围
        @return:
        """
        if self.textWidth == None:
            self.textWidth = self.font.pixelSize() * 4

        rect1, rect2, rect3, rect4 = self.textRect(self.point.x() * self.scale, self.point.y() * self.scale)
        return rect1, rect2, rect3, rect4

    def paint(self, painter, option, widget):
        painter.setPen(Qt.NoPen)
        painter.setBrush(self.labelBrush)
        painter.setRenderHint(QPainter.Antialiasing)

        if self.isSelected():

            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255))
            painter.drawEllipse(self.point * self.scale, self.s_diameter / 2, self.s_diameter / 2)
            painter.setPen(Qt.NoPen)
            painter.setBrush(self.labelBrush)
            painter.drawEllipse(self.point * self.scale, self.s_diameter / 2 * 0.66, self.s_diameter / 2 * 0.66)    # focused的点扩大1.5倍,并且凸显中心点

        elif 0 == self.hoverPointIndex:
            painter.drawEllipse(self.point * self.scale, self.h_diameter / 2, self.h_diameter / 2)
        else:
            painter.drawEllipse(self.point * self.scale, self.diameter / 2, self.diameter / 2)

        if self.drawText:
            painter.setPen(self.textPen)
            painter.setFont(self.font)
            self.textWidth = painter.fontMetrics().boundingRect(self.text()).width()

            rect1, rect2, rect3, rect4 = self.textZone()
            painter.setPen(self.labelPen1)
            painter.setBrush(self.labelBrush1)
            painter.drawRect(rect1)

            painter.setPen(self.labelPen2)
            painter.setBrush(self.labelBrush2)
            painter.drawRect(rect2)

            painter.setPen(self.labelPen1)
            painter.setBrush(self.labelBrush1)
            painter.drawRect(rect3)

            painter.setPen(self.textPen)
            painter.setFont(self.font)
            painter.drawText(rect4, Qt.AlignCenter, self.text())

    def hoverEnterEvent(self, event) -> None:
        if not self.allowInteract:
            return
        return super().hoverEnterEvent(event)

    def hoverMoveEvent(self, event) -> None:
        if not self.allowInteract:
            return
        mPos = event.pos() / self.scale
        # if math.sqrt(pow(mPos.x() - self.point.x(), 2) + pow(mPos.y() - self.point.y(), 2)) <= self.radius / 2:
        self.hoverPointIndex = 0
        self.update()
        return super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event: 'QGraphicsSceneHoverEvent') -> None:
        self.unsetCursor()
        self.hoverPointIndex = None
        self.update()
        return super().hoverLeaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if not self.allowInteract:
            return
        # self.setSelected(True)
        self.selectedItem.emit(self)
        if not self.creating:
            self.moveSrcPoints = self.getPoints()
            # self.focused = True
            self.drawText = False
            self.update()
            self.IsMoving.emit()

    def mouseMoveEvent(self, event) -> None:
        if not self.allowInteract:
            return
        newPoint = event.pos() / self.scale
        self.point = self.pointNormalized(newPoint)
        self.drawText = False
        self.prepareGeometryChange()
        self.moved = True
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if not self.allowInteract:
            return
        if self.creating:
            self.creating = False
            self.creatingSuccess.emit(self.type, self.labelClass)
            self.creatingFinish.emit(self)
        self.MovingDone.emit()
        if self.moveSrcPoints and self.moved:
            self.moveDstPoints = self.getPoints()
            self.posChanged.emit(self.moveSrcPoints, self.moveDstPoints)
        self.moved = False
        self.drawText = True
        self.update()

    def getExport(self):
        dict = super(PointLabel, self).getExport()
        dict["point"] = [self.point.x(), self.point.y()]
        return dict

    def getPoints(self):
        return [self.point]

    def setPoints(self, points):
        assert len(points) == 1
        self.point = points[0]
        self.update()


class TagLabel(Label):
    def __init__(self, point, pRect, cRect, frontColor, backColor, type, operator, confidence):
        super(TagLabel, self).__init__(pRect, cRect, frontColor, backColor, type, operator, confidence)
        self.labelClass = "Tag"
        self.point = point
        # self.origimg = origimg
        self.diameter = 3

    # def boundingRect(self) -> QRectF:
    #     """
    #     用于告知graphicsView如何绘制的区域，需要包含自身
    #     @return:
    #     """
    #     return self.paintRect()

    # def paintRect(self):
    #     """
    #     计算绘制范围的矩形大小
    #     @return:
    #     """
    #     return QRectF(0, 0, self.origimg.width() * self.scale, self.origimg.height() * self.scale)

    def shape(self):
        """
        shape可以比boundingrect更为复杂
        @return:
        """
        temp = QPainterPath()
        temp.setFillRule(Qt.WindingFill)

        # temp.addEllipse(self.point * self.scale, self.radius / 2, self.radius / 2)

        temp.addRect(self.textZone()[0])

        return temp

    def textZone(self):
        """
        用于计算信息区域的显示范围
        @return:
        """
        if self.textWidth == None:
            self.textWidth = self.font.pixelSize() * 4
        rect1, rect2, rect3, rect4 = self.textRect(self.point.x(), self.point.y())
        return rect1, rect2, rect3, rect4

    def paint(self, painter, option, widget):
        painter.setPen(self.selectPen)
        painter.setBrush(self.selectBrush)
        painter.setRenderHint(QPainter.Antialiasing)
        # if self.focused:
        # painter.drawEllipse(self.point, self.radius, self.radius)

        # painter.drawEllipse(self.point, self.radius / 2, self.radius / 2)

        # if self.drawText:
        painter.setPen(self.textPen)
        painter.setFont(self.font)
        self.textWidth = painter.fontMetrics().boundingRect(self.text()).width()

        rect1, rect2, rect3, rect4 = self.textZone()
        painter.setPen(self.labelPen1)
        painter.setBrush(self.labelBrush1)
        painter.drawRect(rect1)

        painter.setPen(self.labelPen2)
        painter.setBrush(self.labelBrush2)
        painter.drawRect(rect2)

        painter.setPen(self.labelPen1)
        painter.setBrush(self.labelBrush1)
        painter.drawRect(rect3)

        painter.setPen(self.textPen)
        painter.setFont(self.font)
        painter.drawText(rect4, Qt.AlignCenter, self.text())

    def getExport(self):
        dict = super(TagLabel, self).getExport()
        dict["point"] = [self.point.x(), self.point.y()]
        return dict

    def getPoints(self):
        return [self.point]

    def setPoints(self, points):
        assert len(points) == 1
        self.point = points[0]
        self.update()

class CircleLabel(Label):

    def __init__(self, circle, pRect, cRect, frontColor, backColor, type, operator, confidence):
        super(CircleLabel, self).__init__(pRect, cRect, frontColor, backColor, type, operator, confidence)
        self.center, self.rx, self.ry = circle
        # self.origimg = origimg
        #A修改
        self.centers = []
        self.show_circle = True

        self.updateColor()
        self.labelClass = "Circle"
        # self.drawText = True
        if self.rx == 0:
            self.creating = True
            self.firstClick = False
    #A修改
    def caculateCenter(self):
        return self.center

    def getAllCenters(self):
        self.centers = [self.caculateCenter()]
        return self.centers

    def drawAllCenters(self, painter):
        painter.setPen(Qt.NoPen)
        painter.setBrush(self.labelBrush)
        for center in self.centers:
            painter.drawEllipse(center, 5, 5)

    def showCenterPoints(self, show):
        if show:
            self.centers = self.getAllCenters()
        else:
            self.centers = []
        self.update()

    def setLabelVisibility(self, visible):
        self.show_circle = visible
        self.setVisible(visible)
        self.update()


    def top(self):
        """
        由于self.rect保存的是原图大小下得绝对位置，需要根据graphicsView中的offset和scale重新计算显示位置的top
        @return:
        """
        return (self.center.y() - self.ry) * self.scale

    def left(self):
        """
        由于self.rect保存的是原图大小下得绝对位置，需要根据graphicsView中的offset和scale重新计算显示位置的left
        @return:
        """
        return (self.center.x() - self.rx) * self.scale

    def width(self):
        """
        由于self.rect保存的是原图大小下得绝对位置，需要根据graphicsView中的offset和scale重新计算显示位置的width
        @return:
        """
        return self.rx * self.scale * 2

    def height(self):
        """
        由于self.rect保存的是原图大小下得绝对位置，需要根据graphicsView中的offset和scale重新计算显示位置的heifht
        @return:
        """
        return self.ry * self.scale * 2

    def shape(self):
        """
        shape可以比boundingrect更为复杂，这里都一样了
        @return:
        """
        temp = QPainterPath()
        temp.setFillRule(Qt.WindingFill)
        if self.creating:
            # boxRect = QRectF(0, 0, self.origimg.width() * self.scale, self.origimg.height() * self.scale)
            boxRect = self.paintRect()
            temp.addRect(boxRect)
        else:
            temp.addEllipse(self.center * self.scale, self.rx * self.scale, self.ry * self.scale)
            temp.addRect(self.textZone()[0])
        return temp

    def textZone(self):
        """
        用于计算信息区域的显示范围，比如框很窄是不是需要多行显示
        @return:
        """
        fPS = self.font.pixelSize()
        if self.textWidth is None:
            self.textWidth = fPS * 4

        rect1, rect2, rect3, rect4 = self.textRect(self.center.x() * self.scale, self.top())
        return rect1, rect2, rect3, rect4

    def pointList(self):
        pointList = [
                self.center * self.scale
            ]
        return pointList

    def paint(self, painter, option, widget):
        painter.setPen(self.selectPen)
        painter.setBrush(self.selectBrush)
        painter.setRenderHint(QPainter.Antialiasing)
        # A修改
        if self.show_circle:
            painter.drawEllipse(self.center * self.scale, self.rx * self.scale, self.ry * self.scale)
        self.drawAllCenters(painter)
        # painter.drawRect(self.boundingRect())
        # 如果被选中就绘制圆心
        # if self.focused:
        if self.isSelected():
            painter.setPen(Qt.NoPen)
            painter.setBrush(self.labelBrush)

            pointList = self.pointList()
            for i in range(len(pointList)):
                point = pointList[i]
                painter.drawEllipse(point, self.diameter / 2, self.diameter / 2)
                if self.hoverPointIndex == i:
                    painter.drawEllipse(point, self.h_diameter / 2, self.h_diameter / 2)

            t_pen = QPen(QColor(255, 255, 255))
            t_pen.setWidth(2)
            t_pen.setStyle(Qt.DotLine)
            painter.setPen(t_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(self.center * self.scale, self.rx * self.scale, self.ry * self.scale)

        if self.drawText:
            painter.setPen(self.textPen)
            painter.setFont(self.font)
            self.textWidth = painter.fontMetrics().boundingRect(self.text()).width()

            rect1, rect2, rect3, rect4 = self.textZone()
            painter.setPen(self.labelPen1)
            painter.setBrush(self.labelBrush1)
            painter.drawRect(rect1)

            painter.setPen(self.labelPen2)
            painter.setBrush(self.labelBrush2)
            painter.drawRect(rect2)

            painter.setPen(self.labelPen1)
            painter.setBrush(self.labelBrush1)
            painter.drawRect(rect3)

            painter.setPen(self.textPen)
            painter.setFont(self.font)
            painter.drawText(rect4, Qt.AlignCenter, self.text())

        # painter.drawEllipse(self.rect.topLeft().x()-5,self.rect.topLeft().y()-5,10,10)
        # painter.drawEllipse(self.rect.topRight().x()-5,self.rect.topRight().y()-5,10,10)

    def hoverEnterEvent(self, event: 'QGraphicsSceneHoverEvent') -> None:
        # print("hover enter&move")
        if not self.allowInteract:
            return
        super(CircleLabel, self).hoverEnterEvent(event)
        pass

    def hoverMoveEvent(self, event: 'QGraphicsSceneHoverEvent') -> None:
        if not self.allowInteract:
            return
        super(CircleLabel, self).hoverMoveEvent(event)
        tPos = event.pos()
        x = tPos.x()
        y = tPos.y()
        if self.creating:
            self.rx = self.ry = math.sqrt(pow(x / self.scale - (self.center.x()), 2) + pow(y / self.scale - (self.center.y()), 2))
            self.prepareGeometryChange()
            self.update()
        # elif self.focused and self.allowMove:
        elif self.isSelected() and self.allowMove:
            # self.initCursor()
            pindex = self.pointInPointList(x, y)
            if pindex != -1:
                cursor = Qt.CrossCursor
                self.hoverPointIndex = pindex
            elif self.pointOnCircle(x, y):
                cursor = self.angle2Cursor(tPos / self.scale, self.center)
                self.hoverPointIndex = None
            else:
                cursor = Qt.SizeAllCursor
                self.hoverPointIndex = None
            self.setCursor(cursor)

    def hoverLeaveEvent(self, event: 'QGraphicsSceneHoverEvent') -> None:
        if not self.allowInteract:
            return
        super(CircleLabel, self).hoverLeaveEvent(event)
        self.unsetCursor()
        self.hoverPointIndex = None
        self.update()

    def angle2Cursor(self, A, B):

        def clockwise_angle(v1, v2):
            x1,y1 = v1
            x2,y2 = v2
            dot = x1*x2+y1*y2
            det = x1*y2-y1*x2
            theta = np.arctan2(det, dot)
            theta = theta if theta>0 else 2*np.pi+theta
            return np.degrees(theta)

        a = np.array((A.x(), A.y()))
        b = np.array((B.x(), B.y()))
        avec = a - b
        bvec = np.array((100, 0))

        a = clockwise_angle(avec, bvec)
        a = a % 180
        if -22.5 < a <= 22.5 or 157.5 < a <= 180:
            cursor = Qt.SizeHorCursor
        elif 22.5 < a <= 67.5:
            cursor = Qt.SizeBDiagCursor
        elif 67.5 < a <= 112.5:
            cursor = Qt.SizeVerCursor
        elif 112.5 < a <= 157.5:
            cursor = Qt.SizeFDiagCursor
        return cursor

    def setNew(self):
        self.i, self.j = 1, 1
        self.adjustPoint = True
        self.adjustBorder = False
        self.drawText = False
        # self.focused = True
        # self.setSelected(True)
        self.selectedItem.emit(self)
        self.MouseInLabelSg.emit(True)

    def mousePressEvent(self, event) -> None:
        if not self.allowInteract:
            return
        # self.focused = True
        # self.setSelected(True)
        self.selectedItem.emit(self)
        tPos = event.pos()
        x = tPos.x()
        y = tPos.y()
        if self.creating:
            if event.buttons() & Qt.RightButton:
                self.rightClicked = True
            else:
                self.rightClicked = False
            if self.rightClicked:
                self.Die = True
                self.hide()
                self.setInteract(False)
                self.creating = False
                self.drawText = True
                self.update()
                self.creatingFinish.emit(self)
            elif self.rx != 0:
                self.creatingSuccess.emit(self.type, self.labelClass)
                self.creatingFinish.emit(self)
                self.drawText = True
                self.creating = False
                self.prepareGeometryChange()
                self.allowMove = True
                event.accept()
                self.update()
            # self.firstClick = False
        else:
            self.moveSrcPoints = self.getPoints()
            # 判断鼠标点击的具体位置
            if self.pointOnCircle(x, y):
                self.adjustPoint = False
                self.adjustBorder = True
                self.drawText = False
                # self.focused = True
                # self.selectedItem.emit(self)
                self.MouseInLabelSg.emit(True)
                self.setCursor(Qt.CrossCursor)
            elif self.pointInCircle(x, y):
                # print("point In Box")
                # self.focused = True
                self.adjustPoint = False
                self.adjustBorder = False
                self.adjustAll = True
                self.lastPos = tPos
                # self.selectedItem.emit(self)
                self.MouseInLabelSg.emit(True)
            else:
                # self.focused = True
                self.MouseInLabelSg.emit(False)
                event.ignore()

    def pointInPointList(self, x, y):
        pointList = self.pointList()
        for i in range(len(pointList)):
            point = pointList[i]
            if self.hoverPointIndex == i:
                diameter = self.h_diameter
            else:
                diameter = self.diameter
            if pow(x - (point.x()), 2) + pow(y - (point.y()), 2) <= pow(diameter / 2, 2):
                return i
        return -1

    def pointOnCircle(self, x, y):
        """
        判断点是否在圆的轮廓线上
        @param x: 点的x
        @param y: 点的y
        @return:
        """
        dist = math.sqrt(pow(x - (self.center.x() * self.scale), 2) + pow(y - (self.center.y() * self.scale), 2))
        if dist <= self.rx + self.penWidth and dist >= self.rx - self.penWidth:
            return True
        return False

    def pointInCircle(self, x, y):
        dist = math.sqrt(pow(x - (self.center.x() * self.scale), 2) + pow(y - (self.center.y() * self.scale), 2))
        if dist < self.rx - self.penWidth:
            return True
        return False

    def mouseMoveEvent(self, event) -> None:
        if not self.allowInteract:
            return
        _tPos = event.pos()
        # event.accept()
        needsave = True
        self.moved = True
        # 移动时需要根据点击位置的不同做出不同的更新
        if self.adjustBorder:
            # 点击的是圆的轮廓
            dist = math.sqrt(pow(_tPos.x() / self.scale - self.center.x(), 2) + pow(_tPos.y() / self.scale - self.center.y(), 2))
            self.rx = self.ry = dist
        elif self.adjustAll:
            # 点击的是整体
            lPos = self.lastPos
            move = (_tPos - lPos) / self.scale
            self.lastPos = _tPos
            newCenter = QPointF(self.center.x() + move.x(), self.center.y() + move.y())
            self.center = self.pointNormalized(newCenter)
        else:
            needsave = False

        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if not self.allowInteract:
            return
        
        self.adjustPoint = False
        self.adjustBorder = False
        self.adjustAll = False
        self.MouseInLabelSg.emit(False)
        # self.needSaveItem.emit(True)
        # self.selectedItem.emit(self)
        if self.creating == False:
            self.drawText = True
        if self.moveSrcPoints and self.moved:
            self.moveDstPoints = self.getPoints()
            self.posChanged.emit(self.moveSrcPoints, self.moveDstPoints)
        self.moveSrcPoints = None
        self.moveDstPoints = None
        self.moved = False
        #A修改
        self.centers = self.getAllCenters()
        self.update()

    def exportMask(self):
        mask = np.zeros((int(self.cRect.height()), int(self.cRect.width())), dtype=np.uint8)
        center = (int(self.center.x()), int(self.center.y()))
        cv2.circle(mask, center, int(self.rx), (255), -1)
        # cv2.fillPoly(mask, [pts], color=(255))
        return mask

    def getExport(self):
        dict = super(CircleLabel, self).getExport()

        dict["center"] = [self.center.x(), self.center.y()]
        dict["radius"] = [self.rx, self.ry]
        return dict

    def getPoints(self):
        return [self.center, QPointF(self.rx, self.ry)]

    def setPoints(self, points):
        assert len(points) == 2
        # topLeft = QPointF(min(points[0].x(), points[1].x()), min(points[0].y(), points[1].y()))
        # bottomRight = QPointF(max(points[0].x(), points[1].x()), max(points[0].y(), points[1].y()))
        self.center =points[0]
        self.rx = points[1].x()
        self.ry = points[1].y()
        self.update()


class ScrawLabel(Label):
    painted = pyqtSignal(QPixmap, QPixmap)
    def __init__(self, pixmap, confmap, origimg, frontColor, backColor, type, operator, confidence):
        super(ScrawLabel, self).__init__(None, None, frontColor, backColor, type, operator, confidence)
        # self.setAcceptedMouseButtons(Qt.LeftButton)
        # self.setFlag()
        self.pixmap = pixmap
        self.origimg = origimg
        if confmap is None and self.origimg is not None:
            self.confmap = np.zeros([self.origimg.height(), self.origimg.width()], dtype=np.uint8)
            self.confmap[np.where(self.confmap == 0)] = 100
            self.computeConf()
        else:
            self.confmap = confmap
        self.oldmap = None
        self.point_list = []

        self.penWidth = 20
        self.painting = True
        self.eraser = False

        self.selected_index = None
        self.moving_all = False
        # self.creating = True
        self.labelClass = "Scraw"

        # self.alphaSelect = 25
        # self.alpha = 50
        self.updateColor()

    def boundingRect(self) -> QRectF:
        """
        用于告知graphicsView如何绘制的区域，需要包含自身
        @return:
        """
        # temprect = self.paintRect()
        # return QRectF(temprect.left()-100,temprect.top()-100,temprect.width()+2000,temprect.height()+2000)

        # return self.paintRect()
        return QRectF(0, 0, self.origimg.width() * self.scale, self.origimg.height() * self.scale)

    def paintRect(self):
        """
        计算绘制范围的矩形大小
        @return:
        """
        # t_rect = self.polygon.boundingRect()

        return QRectF(0, 0, self.origimg.width() * self.scale, self.origimg.height() * self.scale)

    def shape(self):
        qpath = QPainterPath()
        if self.allowInteract:
            qpath.addRect(self.paintRect())
        else:
            qpath.addRect(QRectF(self.origimg.width() / 2 * self.scale, self.origimg.height() / 2 * self.scale, 0, 0))
        return qpath

    def updateColor(self):
        """
        更新该label的颜色，因为有时候癌症类别会变、透明度会变
        @return:
        """

        self.selectPen = QPen()
        t_color = QColor(*self.backColor.getRgb())
        self.alpha = max(1, self.alpha) # 涂鸦的alpha最低为1，否则会出现涂鸦消失的情况
        self.alphaSelect = max(1, self.alphaSelect)
        if self.hover:
            t_color.setAlpha(self.alphaSelect)
        else:
            t_color.setAlpha(self.alpha)
        self.selectColor = t_color
        self.selectPen.setColor(t_color)
        self.selectPen.setWidth(self.penWidth)

        self.eraserPenTrack = QPen()
        self.eraserPenTrack.setColor(QColor(255, 255, 255, 255))
        self.eraserPenTrack.setWidth(self.penWidth)

        self.eraserPen = QPen()
        self.eraserPen.setColor(QColor(255, 255, 255, 0))
        self.eraserPen.setWidth(self.penWidth / 2)

        self.selectBrush = QBrush(Qt.SolidPattern)
        self.selectBrush.setColor(t_color)
        self.eraserBrush = QBrush(Qt.SolidPattern)
        self.eraserBrush.setColor(QColor(255, 255, 255, 0))

        self.MaskColor = QColor(255, 255, 255, 0)
        tempColor = QColor(self.MaskColor.rgba())
        tempColor.setAlpha(0)
        

        self.textPen = QPen()
        self.textPen.setColor(self.frontColor)

        self.labelPen = Qt.NoPen
        self.labelBrush = QBrush(Qt.SolidPattern)
        self.labelBrush.setColor(self.backColor)

        self.font = QFont()
        self.font.setPixelSize(self.fontPixelSize)

        arr = np.array(Image.fromqpixmap(self.pixmap))
        dist = np.zeros((arr.shape[0],arr.shape[1],4), dtype=np.uint8)
        arr = arr.sum(axis=2)

        # test=np.hstack((self.backColor.getRgb()[:3], self.alpha))
        # print(test)

        if self.hover:
            dist[arr > 0, :] = np.hstack((self.backColor.getRgb()[:3], self.alphaSelect))
        else:
            dist[arr > 0, :] = np.hstack((self.backColor.getRgb()[:3], self.alpha))

        # dist[arr > 0, :] = self.backColor.getRgb()

        im = Image.fromarray(dist)
        im = im.toqpixmap()
        self.pixmap = im
        pass

    def paint(self, painter, option, widget):
        #
        
        t_painter = QPainter()
        t_painter.begin(self.pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        t_painter.setRenderHint(QPainter.Antialiasing)
        if self.painting:
            t_painter.setPen(Qt.NoPen)
            t_painter.setBrush(self.selectBrush)
            t_painter.setCompositionMode(QPainter.CompositionMode_Source)
        else:
            t_painter.setPen(Qt.NoPen)
            t_painter.setBrush(self.eraserBrush)
            t_painter.setCompositionMode(QPainter.CompositionMode_Source)
        if self.eraser:
            t_painter.setPen(Qt.NoPen)
            t_painter.setBrush(self.eraserBrush)
            t_painter.setCompositionMode(QPainter.CompositionMode_Source)
        if len(self.point_list) >= 2:
                src, dst = self.point_list[-2], self.point_list[-1]
                length = math.sqrt(math.pow(dst.x() - src.x(), 2) + math.pow(dst.y() - src.y(), 2))
                if length != 0:
                    dx = (dst.x() - src.x()) / length
                    dy = (dst.y() - src.y()) / length
                    for i in range(math.floor(length)):
                        x = src.x() + dx * i
                        y = src.y() + dy * i
                        t_painter.drawEllipse(QPoint(x, y), self.penWidth/2 / self.scale, self.penWidth/2 / self.scale)

        if len(self.point_list) > 0:
            t_painter.drawEllipse(self.point_list[-1], self.penWidth/2 / self.scale, self.penWidth/2 / self.scale)
        t_painter.end()

        painter.drawPixmap(QRect(0, 0, self.origimg.width() * self.scale,
                                 self.origimg.height() * self.scale), self.pixmap)

    def clearScraw(self):
        # 创建一个与原始图像相同大小的空白 QPixmap，并设置为透明
        empty_pixmap = QPixmap(self.origimg.size())
        empty_pixmap.fill(Qt.transparent)

        # 设置新的空 pixmap
        self.oldmap = self.pixmap.copy()
        self.pixmap = empty_pixmap

        # 清空其他数据
        self.point_list.clear()
        self.confmap = np.zeros([self.origimg.height(), self.origimg.width()], dtype=np.uint8)  # 重置 confmap
        self.confmap[np.where(self.confmap == 0)] = 100

        self.painted.emit(self.oldmap, self.pixmap)
        self.update()

    def hoverEnterEvent(self, event: 'QGraphicsSceneHoverEvent') -> None:
        if not self.allowInteract:
            # self.setCursor(Qt.OpenHandCursor)
            return
        self.setCursor(Qt.CrossCursor)
        pass

    def hoverMoveEvent(self, event: 'QGraphicsSceneHoverEvent') -> None:
        # print('paint')
        if not self.allowInteract:
            # self.setCursor(Qt.OpenHandCursor)
            return
        self.setCursor(Qt.CrossCursor)
        pass

    def hoverLeaveEvent(self, event: 'QGraphicsSceneHoverEvent') -> None:
        if not self.allowInteract:
            # self.setCursor(Qt.OpenHandCursor)
            return
        # self.setCursor(Qt.CrossCursor)
        self.unsetCursor()
        pass

    def mousePressEvent(self, event) -> None:
        if not self.allowInteract:
            
            return
        # print("pressed", event.pos())
        if event.buttons() & Qt.LeftButton:
            self.painting = True
        elif event.buttons() & Qt.RightButton:
            self.painting = False
        if len(self.point_list) <= 1:
            self.point_list.append(event.pos() / self.scale)
        else:
            lastPoint = self.point_list[-1]
            self.point_list = [lastPoint, event.pos() / self.scale]
        self.oldmap = self.pixmap.copy()
        self.update()

    def mouseMoveEvent(self, event) -> None:
        if not self.allowInteract:
            return
        if len(self.point_list) <= 1:
            self.point_list.append(event.pos() / self.scale)
        else:
            lastPoint = self.point_list[-1]
            self.point_list = [lastPoint, event.pos() / self.scale]
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if not self.allowInteract:
            return
        # painter = QPainter()
        # painter.begin(self.pixmap)
        # if self.painting:
        #     painter.setPen(self.selectPen)
        #     painter.setBrush(self.selectBrush)
        #     painter.setCompositionMode(QPainter.CompositionMode_Source)
        # else:
        #     painter.setPen(self.eraserPen)
        #     painter.setCompositionMode(QPainter.CompositionMode_Source)
        # if len(self.point_list) >= 2:
        #     for i in range(len(self.point_list) - 1):
        #         painter.drawLine(self.point_list[i], self.point_list[i + 1])
        #         # painter.drawEllipse(self.point_list[i],
        #         #                     self.penWidth/2,
        #         #                     self.penWidth/2)
        # if len(self.point_list) > 0:
        #     painter.drawPoint(self.point_list[-1])
        # painter.end()
        self.moved = False
        
        self.update()
        if self.oldmap:
            self.fillConfmap(self.oldmap, self.pixmap)
            self.painted.emit(self.oldmap, self.pixmap)
        self.oldmap = None
        self.point_list = []
        # self.getExport()

    def maskToPixmapWithThres(self, mask: np.array, thres: int=0):
        thres = int(100 * thres)
        pixmap_np = np.zeros((*mask.shape, 4), dtype=np.uint8)
        pix = self.selectColor.getRgb()
        pixmap_np[np.where(mask > thres)] = pix
        im = Image.fromarray(pixmap_np)
        img = im.toqpixmap()
        # self.fillConfmap(self.pixmap, img)
        # self.painted.emit(self.pixmap, img)
        self.pixmap = img
        self.update()

    def maskToPixmap(self, mask: np.array, thres: int=0):
        thres = int(100 * thres)
        pixmap_np = np.zeros((*mask.shape, 4), dtype=np.uint8)
        pix = self.selectColor.getRgb()
        pixmap_np[np.where(mask > thres)] = pix
        im = Image.fromarray(pixmap_np)
        img = im.toqpixmap()
        # self.fillConfmap(self.pixmap, img)
        self.painted.emit(self.pixmap, img)
        self.pixmap = img
        self.update()

    def maskToPixmap_hover(self, mask: np.array, thres: int=0):
        thres = int(100 * thres)
        pixmap_np = np.zeros((*mask.shape, 4), dtype=np.uint8)
        pix = self.selectColor.getRgb()
        pixmap_np[np.where(mask > thres)] = pix
        im = Image.fromarray(pixmap_np)
        img = im.toqpixmap()
        # self.fillConfmap(self.pixmap, img)
        # self.painted.emit(self.pixmap, img)
        self.pixmap = img
        self.update()

    def addMaskToPixmap(self, mask: np.array, thres: int=0): 
        # pixmap_np = np.zeros((*mask.shape, 4), dtype=np.uint8)
        pixmap_np = lblPixmapToNmp(self.pixmap)
        pix = self.selectColor.getRgb()
        pixmap_np[np.where(mask > thres)] = pix
        im = Image.fromarray(pixmap_np)
        img = im.toqpixmap()
        self.fillConfmap(self.pixmap, img)
        self.painted.emit(self.pixmap, img)
        self.pixmap = img
        self.update()

    def delMaskToPixmap(self, mask: np.array, thres: int=0):
        # pixmap_np = np.zeros((*mask.shape, 4), dtype=np.uint8)
        pixmap_np = lblPixmapToNmp(self.pixmap)
        pix = self.selectColor.getRgb()
        pixmap_np[np.where(mask > thres)] = 0
        im = Image.fromarray(pixmap_np)
        img = im.toqpixmap()
        self.fillConfmap(self.pixmap, img)
        self.painted.emit(self.pixmap, img)
        self.pixmap = img
        self.update()

    def interMaskToPixmap(self, mask: np.array, thres: int=0):
        # 求交集
        # pixmap_np = np.zeros((*mask.shape, 4), dtype=np.uint8)
        pixmap_np = lblPixmapToNmp(self.pixmap)
        pix = self.selectColor.getRgb()
        pixmap_np[np.where(mask <= thres)] = 0
        im = Image.fromarray(pixmap_np)
        img = im.toqpixmap()
        self.fillConfmap(self.pixmap, img)
        self.painted.emit(self.pixmap, img)
        self.pixmap = img
        self.update()


    def addMaskToPixmap_hover(self, mask: np.array, thres: int=0):
        pixmap_np = np.zeros((*mask.shape, 4), dtype=np.uint8)
        # pixmap_np = lblPixmapToNmp(self.pixmap)
        pix = self.selectColor.getRgb()
        pixmap_np[np.where(mask > thres)] = pix
        im = Image.fromarray(pixmap_np)
        img = im.toqpixmap()
        #self.fillConfmap(self.pixmap, img)
        #self.painted.emit(self.pixmap, img)
        self.pixmap = img
        self.update()

    def interMaskToPixmap_hover(self, mask: np.array, thres: int = 0):
        # 求交集
        # pixmap_np = np.zeros((*mask.shape, 4), dtype=np.uint8)
        pixmap_np = lblPixmapToNmp(self.pixmap)
        pix = self.selectColor.getRgb()
        pixmap_np[np.where(mask <= thres)] = 0
        im = Image.fromarray(pixmap_np)
        img = im.toqpixmap()
        #self.fillConfmap(self.pixmap, img)
        #self.painted.emit(self.pixmap, img)
        self.pixmap = img
        self.update()

    def fillConfmap(self, old_map, new_map):
        oldmap_np = lblPixmapToNmp(old_map)
        oldmap_np = oldmap_np.sum(axis=2)
        pixmap_np = lblPixmapToNmp(new_map)
        pixmap_np = pixmap_np.sum(axis=2)

        areaSelected = np.where(oldmap_np != pixmap_np)
        if np.sum(pixmap_np) > 0:
            newconf = 1.0
            # newconf = random.random()
            newconf = 1
        else:
            newconf = 0
        self.confmap[areaSelected] = int(newconf * 100)

    def changeConfThres(self, thres):
        self.threshold = int(thres * 100)
        if not self.confmap.any():
            return
        else:
            self.maskToPixmapWithThres(self.confmap, thres)

    def confThresEnsure(self):
        self.confmap[np.where(self.confmap >= self.threshold)] = 100
        self.confmap[np.where(self.confmap < self.threshold)] = 0
        self.computeConf()

    def computeConf(self):
        if self.confmap is None:
            return
        confmap = np.zeros([self.origimg.height(), self.origimg.width()], dtype=np.float32)
        confmap[np.where(self.confmap > 0)] = 1
        self.confidence = float(np.sum(self.confmap) / np.sum(confmap)) / 100

    def exportContours(self, strategy='largest'):
        mask = lblPixmapToNmp(self.pixmap, True)
        c, hierarchy = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours = []
        for c_ in c:
            c_ = np.array(c_).reshape(-1, 2)
            point_list = []
            for point in c_.tolist():
                point_list.append(QPoint(*point))
            contours.append(point_list)
        # if c:
        #     if strategy == 'concat':  # concatenate all segments
        #         c = np.concatenate([x.reshape(-1, 2) for x in c])
        #     elif strategy == 'largest':  # select largest segment
        #         c = np.array(c[np.array([len(x) for x in c]).argmax()]).reshape(-1, 2)
            # c_list = c.tolist()[0]
            # for c_ in c_list:
            #     point_list = []
            #     for point in c_.tolist():
            #         point_list.append(QPoint(*point))
            #     contours.append(point_list)
        return contours

    def getExport(self):
        byte_array = QByteArray()
        buffer = QBuffer(byte_array)
        buffer.open(QIODevice.WriteOnly)
        self.pixmap.save(buffer, 'PNG')
        imgstr = byte_array.toBase64()

        self.computeConf()
        dict = super(ScrawLabel, self).getExport()
        dict["confidence"] = self.confidence
        dict["label_png"] = str(imgstr)[2:-1]
        dict["conf_map"] = numpyUint8ToBase64(self.confmap)

        return dict

    def getPixmap(self):
        return self.pixmap
    
    def setConfmap(self, confmap):
        self.confmap = confmap

    def getConfmap(self):
        return self.confmap

    def setPixmap(self, pixmap):
        self.oldmap = self.pixmap.copy()
        self.pixmap = pixmap.copy()
        self.fillConfmap(self.oldmap, self.pixmap)
        self.update()


class MouseHoverScrawLabel(Label):
    painted = pyqtSignal(QPixmap, QPixmap)

    def __init__(self, pixmap, confmap, origimg, frontColor, backColor, type, operator, confidence):
        super(MouseHoverScrawLabel, self).__init__(None, None, frontColor, backColor, type, operator, confidence)
        # self.setAcceptedMouseButtons(Qt.LeftButton)
        # self.setFlag()
        self.pixmap = pixmap
        self.origimg = origimg
        if confmap is None and self.origimg is not None:
            self.confmap = np.zeros([self.origimg.height(), self.origimg.width()], dtype=np.uint8)
            self.confmap[np.where(self.confmap == 0)] = 100
            self.computeConf()
        else:
            self.confmap = confmap
        self.oldmap = None
        self.point_list = []

        self.penWidth = 20
        self.painting = True

        self.selected_index = None
        self.moving_all = False
        # self.creating = True
        self.labelClass = "MouseHoverScraw"

        # self.alphaSelect = 25
        # self.alpha = 50
        self.updateColor()

    def boundingRect(self) -> QRectF:
        """
        用于告知graphicsView如何绘制的区域，需要包含自身
        @return:
        """
        # temprect = self.paintRect()
        # return QRectF(temprect.left()-100,temprect.top()-100,temprect.width()+2000,temprect.height()+2000)

        return self.paintRect()

    def paintRect(self):
        """
        计算绘制范围的矩形大小
        @return:
        """
        # t_rect = self.polygon.boundingRect()

        return QRectF(0, 0, self.origimg.width() * self.scale, self.origimg.height() * self.scale)

    def shape(self):
        qpath = QPainterPath()
        if self.allowInteract:
            qpath.addRect(self.paintRect())
        else:
            qpath.addRect(QRectF(self.origimg.width() / 2 * self.scale, self.origimg.height() / 2 * self.scale, 0, 0))
        return qpath

    def updateColor(self):
        """
        更新该label的颜色，因为有时候癌症类别会变、透明度会变
        @return:
        """

        self.selectPen = QPen()
        t_color = QColor(*self.backColor.getRgb())
        self.alpha = max(1, self.alpha)  # 涂鸦的alpha最低为1，否则会出现涂鸦消失的情况
        self.alphaSelect = max(1, self.alphaSelect)
        if self.hover:
            t_color.setAlpha(self.alphaSelect)
        else:
            t_color.setAlpha(self.alpha)
        self.selectColor = t_color
        self.selectPen.setColor(t_color)
        self.selectPen.setWidth(self.penWidth)

        self.eraserPenTrack = QPen()
        self.eraserPenTrack.setColor(QColor(255, 255, 255, 255))
        self.eraserPenTrack.setWidth(self.penWidth)

        self.eraserPen = QPen()
        self.eraserPen.setColor(QColor(255, 255, 255, 0))
        self.eraserPen.setWidth(self.penWidth / 2)

        self.selectBrush = QBrush(Qt.SolidPattern)
        self.selectBrush.setColor(t_color)
        self.eraserBrush = QBrush(Qt.SolidPattern)
        self.eraserBrush.setColor(QColor(255, 255, 255, 0))

        self.MaskColor = QColor(255, 255, 255, 0)
        tempColor = QColor(self.MaskColor.rgba())
        tempColor.setAlpha(0)

        self.textPen = QPen()
        self.textPen.setColor(self.frontColor)

        self.labelPen = Qt.NoPen
        self.labelBrush = QBrush(Qt.SolidPattern)
        self.labelBrush.setColor(self.backColor)

        self.font = QFont()
        self.font.setPixelSize(self.fontPixelSize)

        arr = np.array(Image.fromqpixmap(self.pixmap))
        dist = np.zeros((arr.shape[0], arr.shape[1], 4), dtype=np.uint8)
        arr = arr.sum(axis=2)

        # test=np.hstack((self.backColor.getRgb()[:3], self.alpha))
        # print(test)

        if self.hover:
            dist[arr > 0, :] = np.hstack((self.backColor.getRgb()[:3], self.alphaSelect))
        else:
            dist[arr > 0, :] = np.hstack((self.backColor.getRgb()[:3], self.alpha))

        # dist[arr > 0, :] = self.backColor.getRgb()

        im = Image.fromarray(dist)
        im = im.toqpixmap()
        self.pixmap = im
        pass

    def paint(self, painter, option, widget):
        #

        t_painter = QPainter()
        t_painter.begin(self.pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        t_painter.setRenderHint(QPainter.Antialiasing)
        if self.painting:
            t_painter.setPen(Qt.NoPen)
            t_painter.setBrush(self.selectBrush)
            t_painter.setCompositionMode(QPainter.CompositionMode_Source)
        else:
            t_painter.setPen(Qt.NoPen)
            t_painter.setBrush(self.eraserBrush)
            t_painter.setCompositionMode(QPainter.CompositionMode_Source)
        if len(self.point_list) >= 2:
            src, dst = self.point_list[-2], self.point_list[-1]
            length = math.sqrt(math.pow(dst.x() - src.x(), 2) + math.pow(dst.y() - src.y(), 2))
            if length != 0:
                dx = (dst.x() - src.x()) / length
                dy = (dst.y() - src.y()) / length
                for i in range(math.floor(length)):
                    x = src.x() + dx * i
                    y = src.y() + dy * i
                    t_painter.drawEllipse(QPoint(x, y), self.penWidth / 2 / self.scale, self.penWidth / 2 / self.scale)

        if len(self.point_list) > 0:
            t_painter.drawEllipse(self.point_list[-1], self.penWidth / 2 / self.scale, self.penWidth / 2 / self.scale)
        t_painter.end()

        painter.drawPixmap(QRect(0, 0, self.origimg.width() * self.scale,
                                 self.origimg.height() * self.scale), self.pixmap)

    def hoverEnterEvent(self, event: 'QGraphicsSceneHoverEvent') -> None:
        if not self.allowInteract:
            # self.setCursor(Qt.OpenHandCursor)
            return
        self.setCursor(Qt.CrossCursor)
        pass

    def hoverMoveEvent(self, event: 'QGraphicsSceneHoverEvent') -> None:
        # print('paint')
        if not self.allowInteract:
            # self.setCursor(Qt.OpenHandCursor)
            return
        self.setCursor(Qt.CrossCursor)
        pass

    def hoverLeaveEvent(self, event: 'QGraphicsSceneHoverEvent') -> None:
        if not self.allowInteract:
            # self.setCursor(Qt.OpenHandCursor)
            return
        # self.setCursor(Qt.CrossCursor)
        self.unsetCursor()
        pass

    def mousePressEvent(self, event) -> None:
        if not self.allowInteract:
            return
        # print("pressed", event.pos())
        if event.buttons() & Qt.LeftButton:
            self.painting = True
        elif event.buttons() & Qt.RightButton:
            self.painting = False
        if len(self.point_list) <= 1:
            self.point_list.append(event.pos() / self.scale)
        else:
            lastPoint = self.point_list[-1]
            self.point_list = [lastPoint, event.pos() / self.scale]
        self.oldmap = self.pixmap.copy()
        self.update()

    def mouseMoveEvent(self, event) -> None:
        if not self.allowInteract:
            return
        if len(self.point_list) <= 1:
            self.point_list.append(event.pos() / self.scale)
        else:
            lastPoint = self.point_list[-1]
            self.point_list = [lastPoint, event.pos() / self.scale]
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if not self.allowInteract:
            return
        # painter = QPainter()
        # painter.begin(self.pixmap)
        # if self.painting:
        #     painter.setPen(self.selectPen)
        #     painter.setBrush(self.selectBrush)
        #     painter.setCompositionMode(QPainter.CompositionMode_Source)
        # else:
        #     painter.setPen(self.eraserPen)
        #     painter.setCompositionMode(QPainter.CompositionMode_Source)
        # if len(self.point_list) >= 2:
        #     for i in range(len(self.point_list) - 1):
        #         painter.drawLine(self.point_list[i], self.point_list[i + 1])
        #         # painter.drawEllipse(self.point_list[i],
        #         #                     self.penWidth/2,
        #         #                     self.penWidth/2)
        # if len(self.point_list) > 0:
        #     painter.drawPoint(self.point_list[-1])
        # painter.end()
        self.moved = False

        self.update()
        if self.oldmap:
            self.fillConfmap(self.oldmap, self.pixmap)
            self.painted.emit(self.oldmap, self.pixmap)
        self.oldmap = None
        self.point_list = []
        # self.getExport()

    def maskToPixmap(self, mask: np.array, thres: int = 0):
        thres = int(100 * thres)
        pixmap_np = np.zeros((*mask.shape, 4), dtype=np.uint8)
        pix = self.selectColor.getRgb()
        pixmap_np[np.where(mask > thres)] = pix
        im = Image.fromarray(pixmap_np)
        img = im.toqpixmap()
        # self.fillConfmap(self.pixmap, img)
        # self.painted.emit(self.pixmap, img)
        self.pixmap = img
        self.update()

    def addMaskToPixmap(self, mask: np.array, thres: int = 0):
        # pixmap_np = np.zeros((*mask.shape, 4), dtype=np.uint8)
        pixmap_np = lblPixmapToNmp(self.pixmap)
        pix = self.selectColor.getRgb()
        pixmap_np[np.where(mask > thres)] = pix
        im = Image.fromarray(pixmap_np)
        img = im.toqpixmap()
        self.fillConfmap(self.pixmap, img)
        self.painted.emit(self.pixmap, img)
        self.pixmap = img
        self.update()

    def delMaskToPixmap(self, mask: np.array, thres: int = 0):
        # pixmap_np = np.zeros((*mask.shape, 4), dtype=np.uint8)
        pixmap_np = lblPixmapToNmp(self.pixmap)
        pix = self.selectColor.getRgb()
        pixmap_np[np.where(mask > thres)] = 0
        im = Image.fromarray(pixmap_np)
        img = im.toqpixmap()
        self.fillConfmap(self.pixmap, img)
        self.painted.emit(self.pixmap, img)
        self.pixmap = img
        self.update()

    def fillConfmap(self, old_map, new_map):
        oldmap_np = lblPixmapToNmp(old_map)
        oldmap_np = oldmap_np.sum(axis=2)
        pixmap_np = lblPixmapToNmp(new_map)
        pixmap_np = pixmap_np.sum(axis=2)

        areaSelected = np.where(oldmap_np != pixmap_np)
        if np.sum(pixmap_np) > 0:
            newconf = 1.0
            # newconf = random.random()
            newconf = 1
        else:
            newconf = 0
        self.confmap[areaSelected] = int(newconf * 100)

    def changeConfThres(self, thres):
        self.threshold = int(thres * 100)
        if not self.confmap.any():
            return
        else:
            self.maskToPixmap(self.confmap, thres)

    def confThresEnsure(self):
        self.confmap[np.where(self.confmap >= self.threshold)] = 100
        self.confmap[np.where(self.confmap < self.threshold)] = 0
        self.computeConf()

    def computeConf(self):
        if self.confmap is None:
            return
        confmap = np.zeros([self.origimg.height(), self.origimg.width()], dtype=np.float32)
        confmap[np.where(self.confmap > 0)] = 1
        self.confidence = float(np.sum(self.confmap) / np.sum(confmap)) / 100

    def exportContours(self, strategy='largest'):
        mask = lblPixmapToNmp(self.pixmap, True)
        c, hierarchy = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours = []
        for c_ in c:
            c_ = np.array(c_).reshape(-1, 2)
            point_list = []
            for point in c_.tolist():
                point_list.append(QPoint(*point))
            contours.append(point_list)
        # if c:
        #     if strategy == 'concat':  # concatenate all segments
        #         c = np.concatenate([x.reshape(-1, 2) for x in c])
        #     elif strategy == 'largest':  # select largest segment
        #         c = np.array(c[np.array([len(x) for x in c]).argmax()]).reshape(-1, 2)
        # c_list = c.tolist()[0]
        # for c_ in c_list:
        #     point_list = []
        #     for point in c_.tolist():
        #         point_list.append(QPoint(*point))
        #     contours.append(point_list)
        return contours

    def getExport(self):
        byte_array = QByteArray()
        buffer = QBuffer(byte_array)
        buffer.open(QIODevice.WriteOnly)
        self.pixmap.save(buffer, 'PNG')
        imgstr = byte_array.toBase64()

        self.computeConf()
        dict = super(MouseHoverScrawLabel, self).getExport()
        dict["confidence"] = self.confidence
        dict["label_png"] = str(imgstr)[2:-1]
        dict["conf_map"] = numpyUint8ToBase64(self.confmap)

        return dict

    def getPixmap(self):
        return self.pixmap

    def setConfmap(self, confmap):
        self.confmap = confmap

    def getConfmap(self):
        return self.confmap

    def setPixmap(self, pixmap):
        self.oldmap = self.pixmap.copy()
        self.pixmap = pixmap.copy()
        self.fillConfmap(self.oldmap, self.pixmap)
        self.update()


class ScrawCursor(QGraphicsObject):
    def __init__(self, imgWidth, imgHeight, imgScale=1.0, alpha=50):
        super(ScrawCursor, self).__init__()
        self.cursorWidth = 20
        self.cusorPos = QPointF()

        self.imgWidth = imgWidth
        self.imgHeight = imgHeight
        self.imgScale = imgScale

        self.pen = QPen()
        self.penColor = QColor(255, 255, 255)
        self.brush = QBrush(Qt.SolidPattern)
        self.brushColor = QColor(255, 255, 255)
        self.oldColor = QColor(255, 255, 255)
        self.alpha = alpha

    def boundingRect(self):
        return QRectF(0, 0, self.imgWidth * self.imgScale, self.imgHeight * self.imgScale)

    def shape(self):
        path = QPainterPath()
        ellipse = QRectF(self.cusorPos.x() - self.cursorWidth / 2, self.cusorPos.y() - self.cursorWidth / 2, self.cursorWidth, self.cursorWidth)
        path.addEllipse(ellipse)
        return path

    def paint(self, painter, option, widget) -> None:
        # t_color = QColor(*self.penColor.getRgb())
        # t_color.setAlpha(self.alpha)
        painter.setRenderHint(QPainter.Antialiasing)
        self.pen.setColor(self.penColor)
        # self.brush.setColor(t_color)

        painter.setBrush(Qt.NoBrush)
        painter.setPen(self.pen)

        painter.drawEllipse(self.cusorPos, self.cursorWidth / 2, self.cursorWidth / 2)
        # return super().paint(painter, option, widget)

    # def mousePressEvent(self, event) -> None:
    #     self.oldColor = self.penColor
    #     self.penColor = QColor(255, 255, 255)
    #     self.update()
    #     return super().mousePressEvent(event)

    # def mouseReleaseEvent(self, event: 'QGraphicsSceneMouseEvent') -> None:
    #     self.penColor = self.oldColor
    #     self.update()
    #     return super().mouseReleaseEvent(event)

    def updateScrawCursor(self, pos, color):
        self.cusorPos = pos
        self.penColor = color if color != QColor(255, 255, 255) else QColor(255, 255, 255)
        self.brushColor = color
        self.update()

    def keyPressEvent(self, event) -> None:
        event.accept()
        return super().keyPressEvent(event)


def euclideanDistance(p, q):
    return math.sqrt((p.x() - q.x()) ** 2 + (p.y() - q.y()) ** 2)


class Rect_mask_Label(Label):

    def __init__(self, rect, pRect, cRect, frontColor, backColor, type, operator, confidence):
        super(Rect_mask_Label, self).__init__(pRect, cRect, frontColor, backColor, type, operator, confidence)
        self.rect = rect
        self.updateColor()
        self.labelClass = "Rectangle"
        # self.drawText = True
        if rect.isEmpty():
            self.creating = True
        # self.setFlag(QGraphicsObject.ItemIsMovable)
        self.srcPos = self.rect.topLeft()

    def top(self):
        """
        由于self.rect保存的是原图大小下得绝对位置，需要根据graphicsView中的offset和scale重新计算显示位置的top
        @return:
        """
        return self.rect.top() * self.scale

    def left(self):
        """
        由于self.rect保存的是原图大小下得绝对位置，需要根据graphicsView中的offset和scale重新计算显示位置的left
        @return:
        """
        return self.rect.left() * self.scale

    def width(self):
        """
        由于self.rect保存的是原图大小下得绝对位置，需要根据graphicsView中的offset和scale重新计算显示位置的width
        @return:
        """
        return self.rect.width() * self.scale

    def height(self):
        """
        由于self.rect保存的是原图大小下得绝对位置，需要根据graphicsView中的offset和scale重新计算显示位置的heifht
        @return:
        """
        return self.rect.height() * self.scale

    # def boundingRect(self) -> QRectF:
    #     """
    #     用于告知graphicsView如何绘制的区域，需要包含自身
    #     @return:
    #     """
    #     # temprect = self.paintRect()
    #     # return QRectF(temprect.left()-100,temprect.top()-100,temprect.width()+2000,temprect.height()+2000)

    #     return self.paintRect()

    # def paintRect(self):
    #     """
    #     计算绘制范围的矩形大小
    #     @return:
    #     """
    #     if self.origimg:
    #         return QRectF(0, 0, self.origimg.width() * self.scale, self.origimg.height() * self.scale)
    #     else:
    #         pW = self.selectPen.width()
    #         if self.drawText:
    #             tRect = self.textZone()[0]
    #             # 此处加的offset为防止标签部分渲染擦除失效
    #             tW = tRect.width() + 20
    #             tH = tRect.height()
    #             return QRectF(self.left() - self.diameter / 2, self.top() - tH, max(self.width() + self.diameter, tW),
    #                         self.height() + tH + self.diameter)
    #         else:
    #             return QRectF(self.left() - self.diameter / 2, self.top() - self.diameter / 2, self.width() + self.diameter,
    #                         self.height() + self.diameter)

    def shape(self):
        """
        shape可以比boundingrect更为复杂，这里都一样了
        @return:
        """
        # pW = self.selectPen.width()
        # if self.drawText:
        #     tRect = self.textZone()
        #     tW = tRect.width()
        #     tH = tRect.height()
        #
        #
        #     return QRectF(self.left() - self.radius / 2, self.top() - tH, max(self.width() + self.radius, tW),
        #                   self.height() + tH + self.radius)
        # else:
        #     return QRectF(self.left() - self.radius / 2, self.top() - self.radius / 2, self.width() + self.radius,
        #                   self.height() + self.radius)
        temp = QPainterPath()
        temp.setFillRule(Qt.WindingFill)
        if self.creating:
            # boxRect = QRectF(0, 0, self.origimg.width() * self.scale, self.origimg.height() * self.scale)
            boxRect = self.paintRect()
            temp.addRect(boxRect)
        else:
            # boxRect = QRectF(self.left() - self.diameter / 2, self.top() - self.diameter / 2, self.width() + self.diameter,
            #                     self.height() + self.diameter)

            boxRect = QRectF(self.left(), self.top(), self.width(), self.height())
            temp.addRect(boxRect)
            temp.addRect(self.textZone()[0])
            if self.isSelected():
                pointList = self.pointList()
                for i in range(len(pointList)):
                    point = pointList[i]
                    temp.addEllipse(point, self.diameter / 2, self.diameter / 2)
                    if self.hoverPointIndex == i:
                        temp.addEllipse(point, self.h_diameter / 2, self.h_diameter / 2)
        return temp

    def textZone(self):
        """
        用于计算信息区域的显示范围，比如框很窄是不是需要多行显示
        @return:
        """
        fPS = self.font.pixelSize()
        if self.textWidth is None:
            self.textWidth = fPS * 4

        rect1, rect2, rect3, rect4 = self.textRect(self.left(), self.top())
        return rect1, rect2, rect3, rect4

    def pointList(self):
        pointList = [
            QPointF(self.left(), self.top()),  # 左上
            QPointF(self.left() + self.width(), self.top()),  # 右上
            QPointF(self.left(), self.top() + self.height()),  # 左下
            QPointF(self.left() + self.width(), self.top() + self.height()),  # 右下

            QPointF(self.left() + self.width() / 2, self.top()),  # 上
            QPointF(self.left(), self.top() + self.height() / 2),  # 左
            QPointF(self.left() + self.width(), self.top() + self.height() / 2),  # 右
            QPointF(self.left() + self.width() / 2, self.top() + self.height()),  # 下
        ]
        return pointList

    def paint(self, painter, option, widget):

        painter.setPen(self.selectPen)
        painter.setBrush(self.selectBrush)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.drawRect(QRectF(self.left(), self.top(), self.width(), self.height()))

        # 如果被选中就绘制四个角的圆圈
        # if self.focused:
        if self.isSelected():
            painter.setPen(Qt.NoPen)
            painter.setBrush(self.labelBrush)
            # painter.drawPath(self.shape())

            pointList = self.pointList()
            for i in range(len(pointList)):
                point = pointList[i]
                painter.drawEllipse(point, self.diameter / 2, self.diameter / 2)
                if self.hoverPointIndex == i:
                    painter.drawEllipse(point, self.h_diameter / 2, self.h_diameter / 2)

            # painter.drawEllipse(self.left() - self.radius / 2, self.top() - self.radius / 2, self.radius, self.radius)
            # painter.drawEllipse(self.left() + self.width() - self.radius / 2, self.top() - self.radius / 2, self.radius,
            #                     self.radius)
            # painter.drawEllipse(self.left() - self.radius / 2, self.top() + self.height() - self.radius / 2,
            #                     self.radius, self.radius)
            # painter.drawEllipse(self.left() + self.width() - self.radius / 2,
            #                     self.top() + self.height() - self.radius / 2, self.radius, self.radius)

            # painter.drawEllipse(self.left() + self.width() / 2 - self.radius / 2, self.top() - self.radius / 2, self.radius, self.radius)
            # painter.drawEllipse(self.left() - self.radius / 2, self.top() + self.height() / 2 - self.radius / 2, self.radius,
            #                     self.radius)
            # painter.drawEllipse(self.left() + self.width() / 2 - self.radius / 2, self.top() + self.height() - self.radius / 2,
            #                     self.radius, self.radius)
            # painter.drawEllipse(self.left() + self.width() - self.radius / 2,
            #                     self.top() + self.height() / 2 - self.radius / 2, self.radius, self.radius)

            t_pen = QPen(QColor(255, 255, 255))
            t_pen.setWidth(2)
            t_pen.setStyle(Qt.DotLine)
            painter.setPen(t_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(QRectF(self.left(), self.top(), self.width(), self.height()))

        # painter.setPen(QPen(Qt.black, 2, Qt.SolidLine))
        # painter.drawPath(self.shape())
        if self.drawText:
            painter.setPen(self.textPen)
            painter.setFont(self.font)
            self.textWidth = painter.fontMetrics().boundingRect(self.text()).width()

            # painter.setPen(self.labelPen)
            # painter.setBrush(self.labelBrush)
            # painter.drawRect(self.textZone())

            rect1, rect2, rect3, rect4 = self.textZone()
            painter.setPen(self.labelPen1)
            painter.setBrush(self.labelBrush1)
            painter.drawRect(rect1)

            painter.setPen(self.labelPen2)
            painter.setBrush(self.labelBrush2)
            painter.drawRect(rect2)

            painter.setPen(self.labelPen1)
            painter.setBrush(self.labelBrush1)
            painter.drawRect(rect3)

            painter.setPen(self.textPen)
            painter.setFont(self.font)
            painter.drawText(rect4, Qt.AlignCenter, self.text())

        # painter.drawEllipse(self.rect.topLeft().x()-5,self.rect.topLeft().y()-5,10,10)
        # painter.drawEllipse(self.rect.topRight().x()-5,self.rect.topRight().y()-5,10,10)

    def hoverEnterEvent(self, event: 'QGraphicsSceneHoverEvent') -> None:
        # print("hover enter&move")
        if not self.allowInteract:
            return
        super(Rect_mask_Label, self).hoverEnterEvent(event)
        self.unsetCursor()
        pass

    def hoverMoveEvent(self, event: 'QGraphicsSceneHoverEvent') -> None:
        if not self.allowInteract:
            return
        super(Rect_mask_Label, self).hoverMoveEvent(event)
        tPos = event.pos()
        if self.creating:
            nPos = self.pointNormalized(tPos / self.scale)
            x = nPos.x()
            y = nPos.y()
            topLeft = QPointF(min(self.srcPos.x(), x), min(self.srcPos.y(), y))
            bottomRight = QPointF(max(self.srcPos.x(), x), max(self.srcPos.y(), y))
            self.rect = QRectF(topLeft, bottomRight)
            self.prepareGeometryChange()
            self.update()
        elif self.isSelected() and self.allowMove:
            pindex = self.pointInPointList(tPos.x(), tPos.y())
            if pindex != -1:
                self.hoverPointIndex = pindex
                if pindex in [0, 3]:
                    self.setCursor(Qt.SizeFDiagCursor)
                elif pindex in [1, 2]:
                    self.setCursor(Qt.SizeBDiagCursor)
                elif pindex in [4, 7]:
                    self.setCursor(Qt.SizeVerCursor)
                elif pindex in [5, 6]:
                    self.setCursor(Qt.SizeHorCursor)
            elif self.pointInBox(tPos.x(), tPos.y()):
                self.setCursor(Qt.SizeAllCursor)
                self.hoverPointIndex = None
            else:
                self.hoverPointIndex = None
                event.ignore()
            self.update()

    def hoverLeaveEvent(self, event: 'QGraphicsSceneHoverEvent') -> None:
        if not self.allowInteract:
            return
        super(Rect_mask_Label, self).hoverLeaveEvent(event)
        self.unsetCursor()
        self.hoverPointIndex = None
        self.update()

    def setNew(self):
        self.i, self.j = 1, 1
        self.adjustPoint = True
        self.adjustBorder = False
        self.drawText = False
        # self.focused = True
        self.setSelected(True)
        self.selectedItem.emit(self)
        self.MouseInLabelSg.emit(True)

    def pointInPointList(self, x, y):
        pointList = self.pointList()
        for i in range(len(pointList)):
            point = pointList[i]
            if self.hoverPointIndex == i:
                diameter = self.h_diameter
            else:
                diameter = self.diameter
            if pow(x - (point.x()), 2) + pow(y - (point.y()), 2) <= pow(diameter / 2, 2):
                return i
        return -1

    def pointInBox(self, x, y):
        """
        判断点击位置是否在label的矩形框内
        @param x: 鼠标点击的x
        @param y: 鼠标点击的y
        @return:
        """
        if self.pointInRect(x, y, QRect(self.left(), self.top(), self.width(), self.height())):
            return True
        else:
            return False

    def pointInBorder(self, x, y):
        """
        判断点击位置是否在四条边上
        @param x: 鼠标点击的x
        @param y: 鼠标点击的y
        @return:
        """
        pW = self.selectPen.width()
        if self.pointInRect(x, y, QRect(self.left() - pW / 2, self.top() - pW / 2, self.width() + pW, pW)):
            return (0, 0)
        elif self.pointInRect(x, y,
                              QRect(self.left() - pW / 2, self.top() + self.height() - pW / 2, self.width() + pW, pW)):
            return (1, 0)
        elif self.pointInRect(x, y, QRect(self.left() - pW / 2, self.top() - pW / 2, pW, self.height() + pW)):
            return (0, 1)
        elif self.pointInRect(x, y,
                              QRect(self.left() + self.width() - pW / 2, self.top() - pW / 2, pW, self.height() + pW)):
            return (1, 1)
        else:
            return False

    def pointInBorderPoint(self, x, y):
        """
        判断点是否在四个角的四条边上
        @param x: 点的x
        @param y: 点的y
        @return:
        """
        pW = self.selectPen.width()
        if pow(x - (self.left() + self.width() / 2), 2) + pow(y - (self.top()), 2) <= pow(self.h_diameter / 2,
                                                                                          2) and self.hoverPointIndex == 4:  # 上
            return (0, 0)
        elif pow(x - (self.left() + self.width() / 2), 2) + pow(y - (self.top() + self.height()), 2) <= pow(
                self.h_diameter / 2, 2 and self.hoverPointIndex == 7):  # 下
            return (1, 0)
        elif pow(x - (self.left()), 2) + pow(y - (self.top() + self.height() / 2), 2) <= pow(self.h_diameter / 2,
                                                                                             2) and self.hoverPointIndex == 5:  # 左
            return (0, 1)
        elif pow(x - (self.left() + self.width()), 2) + pow(y - (self.top() + self.height() / 2), 2) <= pow(
                self.h_diameter / 2, 2) and self.hoverPointIndex == 6:  # 右
            return (1, 1)
        else:
            return False

    def pointInRect(self, x, y, rect):
        """
        判断点是否在指定矩形内
        @param x: 点的x
        @param y: 点的y
        @param rect: 指定的矩形
        @return:
        """
        tRect = rect
        if x >= tRect.left() and x <= tRect.right() and y >= tRect.top() and y <= tRect.bottom():
            return True

    def pointInCircle(self, x, y):
        """
        判断点是否在四个角的圆圈中
        @param x: 点的x
        @param y: 点的y
        @return:
        """
        for i in range(2):
            for j in range(2):
                if pow(x - (self.left() + i * self.width()), 2) + pow(y - (self.top() + j * self.height()), 2) <= pow(
                        self.h_diameter / 2, 2):
                    return (i, j)
        return False

    def contourNormalized(self):
        topleft, bottomright = self.rect.topLeft(), self.rect.bottomRight()
        ox, oy = self.posOffset([topleft, bottomright])
        # topleft += QPointF(ox, oy)
        # bottomright += QPointF(ox, oy)
        self.rect.translate(ox, oy)

    def mousePressEvent(self, event) -> None:
        if not self.allowInteract:
            return
        self.selectedItem.emit(self)
        self.origRect = QRectF(self.rect)
        tPos = event.pos()
        x = tPos.x()
        y = tPos.y()
        if self.creating:
            if self.rect.topLeft() != self.rect.bottomRight():
                self.creatingFinish.emit(self)
                # self.drawText = True
                self.creating = False
                self.prepareGeometryChange()
                self.update()
                self.allowMove = True
        else:
            self.moveSrcPoints = self.getPoints()
            pindex = self.pointInPointList(tPos.x(), tPos.y())
            # 判断鼠标点击的具体位置
            # if self.pointInCircle(x, y):
            if pindex in [0, 1, 2, 3]:
                # self.i, self.j = self.pointInCircle(x, y)
                rectPointIndex = [
                    [0, 0], [1, 0], [0, 1], [1, 1]
                ]
                self.i, self.j = rectPointIndex[pindex]
                self.adjustPoint = True
                self.adjustBorder = False
                self.drawText = False
                # self.focused = True
                # self.selectedItem.emit(self)
                self.MouseInLabelSg.emit(True)
                self.setCursor(Qt.CrossCursor)
            # elif self.pointInBorderPoint(x, y):
            elif pindex in [4, 5, 6, 7]:
                # self.i, self.j = self.pointInBorderPoint(x, y)
                rectPointIndex = [
                    [0, 0], [0, 1], [1, 1], [1, 0]
                ]
                self.i, self.j = rectPointIndex[pindex - 4]
                self.adjustBorder = True
                self.adjustPoint = False
                self.drawText = False
                # self.focused = True
                # self.selectedItem.emit(self)
                self.MouseInLabelSg.emit(True)
                self.setCursor(Qt.CrossCursor)
            # elif self.pointInBox(x, y):
            else:
                # print("point In Box")
                # self.focused = True
                self.adjustPoint = False
                self.adjustBorder = False
                self.adjustAll = True
                self.lastPos = tPos
                # self.selectedItem.emit(self)
                self.MouseInLabelSg.emit(True)
            # else:
            #     # self.focused = True
            #     self.MouseInLabelSg.emit(False)
            #     event.ignore()

    def mouseMoveEvent(self, event) -> None:
        if not self.allowInteract:
            return
        tPos = event.pos()
        # event.accept()
        needsave = True
        self.moved = True
        # 移动时需要根据点击位置的不同做出不同的更新
        if self.adjustPoint:
            # print(tPos)
            # 点击的是四个角
            if self.i == 0 and self.j == 0:
                self.moveLeftTop(self.pointNormalized(tPos / self.scale))
                # print("LeftTop")
            elif self.i == 0 and self.j == 1:
                self.moveLeftBottom(self.pointNormalized(tPos / self.scale))
                # print("LeftBottom")
            elif self.i == 1 and self.j == 0:
                self.moveRightTop(self.pointNormalized(tPos / self.scale))
                # print("RightTop")
            elif self.i == 1 and self.j == 1:
                self.moveRightBottom(self.pointNormalized(tPos / self.scale))
                # print("RightBottom")
        elif self.adjustBorder:
            # 点击的是一个边
            if self.i == 0 and self.j == 0:
                self.moveTop(self.pointNormalized(tPos / self.scale))
                # print("Top")
            elif self.i == 0 and self.j == 1:
                self.moveLeft(self.pointNormalized(tPos / self.scale))
                # print("Left")
            elif self.i == 1 and self.j == 0:
                self.moveBottom(self.pointNormalized(tPos / self.scale))
                # print("Bottom")
            elif self.i == 1 and self.j == 1:
                self.moveRight(self.pointNormalized(tPos / self.scale))
                # print("Right")
        elif self.adjustAll:
            # 点击的是整体
            lPos = self.lastPos
            move = tPos - lPos
            self.lastPos = tPos
            self.rect.translate(move.x() / self.scale, move.y() / self.scale)
            self.contourNormalized()
        else:
            needsave = False

        self.update()

    def moveTop(self, pos):
        self.rect = QRectF(self.origRect.left(), pos.y(), self.origRect.width(),
                           self.origRect.bottom() - pos.y()).normalized()

    def moveRight(self, pos):
        self.rect = QRectF(self.origRect.left(), self.origRect.top(), pos.x() - self.origRect.left(),
                           self.origRect.height()).normalized()

    def moveLeft(self, pos):
        self.rect = QRectF(pos.x(), self.origRect.top(), self.origRect.right() - pos.x(),
                           self.origRect.height()).normalized()

    def moveBottom(self, pos):
        self.rect = QRectF(self.origRect.left(), self.origRect.top(), self.origRect.width(),
                           pos.y() - self.origRect.top()).normalized()

    def moveLeftTop(self, pos):
        self.rect = QRectF(pos, self.origRect.bottomRight()).normalized()

    def moveLeftBottom(self, pos):
        self.rect = QRectF(pos.x(), self.origRect.top(), self.origRect.right() - pos.x(),
                           pos.y() - self.origRect.top()).normalized()

    def moveRightTop(self, pos):
        self.rect = QRectF(self.origRect.left(), pos.y(), pos.x() - self.origRect.left(),
                           self.origRect.bottom() - pos.y()).normalized()

    def moveRightBottom(self, pos):
        self.rect = QRectF(self.origRect.topLeft(), pos).normalized()

    def mouseReleaseEvent(self, event) -> None:
        if not self.allowInteract:
            return
        # print("release:"+str(event.pos()))
        # print(str(self.rect))

        self.adjustPoint = False
        self.adjustBorder = False
        self.adjustAll = False
        self.MouseInLabelSg.emit(False)
        # self.needSaveItem.emit(True)
        # self.selectedItem.emit(self)
        if self.creating == False:
            self.drawText = True
        if self.moveSrcPoints and self.moved:
            self.moveDstPoints = self.getPoints()
            self.posChanged.emit(self.moveSrcPoints, self.moveDstPoints)
        self.moveSrcPoints = None
        self.moveDstPoints = None
        self.moved = False
        self.update()
        #     self.creatingFinish.emit()
        #     self.creating = False

    def exportMask(self):
        mask = np.zeros((int(self.cRect.height()), int(self.cRect.width())), dtype=np.uint8)
        x1 = int(self.rect.left())
        y1 = int(self.rect.top())
        x2 = int(self.rect.right())
        y2 = int(self.rect.bottom())
        pts = np.array([[x1, y1], [x2, y1], [x2, y2], [x1, y2]], np.int32)
        cv2.fillPoly(mask, [pts], color=(255))
        return mask

    def getExport(self):
        dict = super(Rect_mask_Label, self).getExport()

        dict["left"] = self.rect.left()
        dict["top"] = self.rect.top()
        dict["width"] = self.rect.width()
        dict["height"] = self.rect.height()
        return dict

    def getPoints(self):
        return [self.rect.topLeft(), self.rect.bottomRight()]

    def setPoints(self, points):
        assert len(points) == 2
        # topLeft = QPointF(min(points[0].x(), points[1].x()), min(points[0].y(), points[1].y()))
        # bottomRight = QPointF(max(points[0].x(), points[1].x()), max(points[0].y(), points[1].y()))
        self.rect = QRectF(points[0], points[1])
        self.update()


class Feedback_PointLabel(Label):
    IsMoving = pyqtSignal()
    MovingDone = pyqtSignal()
    def __init__(self, point, pRect, cRect, frontColor, backColor, type, operator, confidence):
        super(Feedback_PointLabel, self).__init__(pRect, cRect, frontColor, backColor, type, operator, confidence)
        self.labelClass = "Feedback"
        self.point = point
        # self.origimg = origimg
        self.diameter /= 2
        self.creating = True
        self.allowInteract = False
        self.setFlag(QGraphicsObject.ItemIsSelectable, False)


    def shape(self):
        """
        shape可以比boundingrect更为复杂
        @return:
        """
        temp = QPainterPath()
        temp.setFillRule(Qt.WindingFill)
        if self.isSelected():
            temp.addEllipse(self.point * self.scale, self.s_diameter / 2, self.s_diameter / 2)
        elif self.hoverPointIndex == 0:
            temp.addEllipse(self.point * self.scale, self.h_diameter / 2, self.h_diameter / 2)
        else:
            temp.addEllipse(self.point * self.scale, self.diameter / 2, self.diameter / 2)
        if self.drawText:
            temp.addRect(self.textZone()[0])

        return temp

    def textZone(self):
        """
        用于计算信息区域的显示范围
        @return:
        """
        if self.textWidth == None:
            self.textWidth = self.font.pixelSize() * 4

        rect1, rect2, rect3, rect4 = self.textRect(self.point.x() * self.scale, self.point.y() * self.scale)
        return rect1, rect2, rect3, rect4

    def paint(self, painter, option, widget):
        painter.setPen(Qt.NoPen)
        painter.setBrush(self.labelBrush)
        painter.setRenderHint(QPainter.Antialiasing)

        if self.isSelected():

            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255))
            painter.drawEllipse(self.point * self.scale, self.s_diameter / 2, self.s_diameter / 2)
            painter.setPen(Qt.NoPen)
            painter.setBrush(self.labelBrush)
            painter.drawEllipse(self.point * self.scale, self.s_diameter / 2 * 0.66, self.s_diameter / 2 * 0.66)    # focused的点扩大1.5倍,并且凸显中心点

        elif 0 == self.hoverPointIndex:
            painter.drawEllipse(self.point * self.scale, self.h_diameter / 2, self.h_diameter / 2)
        else:
            painter.drawEllipse(self.point * self.scale, self.diameter / 2, self.diameter / 2)

        # if self.drawText:
        #     painter.setPen(self.textPen)
        #     painter.setFont(self.font)
        #     self.textWidth = painter.fontMetrics().boundingRect(self.text()).width()
        #
        #     rect1, rect2, rect3, rect4 = self.textZone()
        #     painter.setPen(self.labelPen1)
        #     painter.setBrush(self.labelBrush1)
        #     painter.drawRect(rect1)
        #
        #     painter.setPen(self.labelPen2)
        #     painter.setBrush(self.labelBrush2)
        #     painter.drawRect(rect2)
        #
        #     painter.setPen(self.labelPen1)
        #     painter.setBrush(self.labelBrush1)
        #     painter.drawRect(rect3)
        #
        #     painter.setPen(self.textPen)
        #     painter.setFont(self.font)
        #     painter.drawText(rect4, Qt.AlignCenter, self.text())

    # def hoverEnterEvent(self, event) -> None:
    #     if not self.allowInteract:
    #         return
    #     return super().hoverEnterEvent(event)
    #
    # def hoverMoveEvent(self, event) -> None:
    #     if not self.allowInteract:
    #         return
    #     mPos = event.pos() / self.scale
    #     # if math.sqrt(pow(mPos.x() - self.point.x(), 2) + pow(mPos.y() - self.point.y(), 2)) <= self.radius / 2:
    #     self.hoverPointIndex = 0
    #     self.update()
    #     return super().hoverMoveEvent(event)
    #
    # def hoverLeaveEvent(self, event: 'QGraphicsSceneHoverEvent') -> None:
    #     self.unsetCursor()
    #     self.hoverPointIndex = None
    #     self.update()
    #     return super().hoverLeaveEvent(event)

    # def mousePressEvent(self, event) -> None:
    #     if not self.allowInteract:
    #         return
    #     # self.setSelected(True)
    #     self.selectedItem.emit(self)
    #     if not self.creating:
    #         self.moveSrcPoints = self.getPoints()
    #         # self.focused = True
    #         self.drawText = False
    #         self.update()
    #         self.IsMoving.emit()
    #
    # def mouseMoveEvent(self, event) -> None:
    #     if not self.allowInteract:
    #         return
    #     # offset = (event.pos() - event.lastPos()) / self.scale
    #     # newPoint = self.point + offset
    #     newPoint = event.pos()
    #     self.point = self.pointNormalized(newPoint)
    #     self.drawText = False
    #     self.prepareGeometryChange()
    #     self.moved = True
    #     self.update()
    #
    # def mouseReleaseEvent(self, event) -> None:
    #     if not self.allowInteract:
    #         return
    #     if self.creating:
    #         self.creating = False
    #         self.creatingFinish.emit(self)
    #     self.MovingDone.emit()
    #     if self.moveSrcPoints and self.moved:
    #         self.moveDstPoints = self.getPoints()
    #         self.posChanged.emit(self.moveSrcPoints, self.moveDstPoints)
    #     self.moved = False
    #     self.drawText = True
    #     self.update()

    def getExport(self):
        dict = super(Feedback_PointLabel, self).getExport()
        dict["point"] = [self.point.x(), self.point.y()]
        return dict

    def getPoints(self):
        return [self.point]

    def setPoints(self, points):
        assert len(points) == 1
        self.point = points[0]
        self.update()

class PreSeg_ScrawLabel(ScrawLabel):
    painted = pyqtSignal(QPixmap, QPixmap)
    def __init__(self, pixmap, confmap, origimg, frontColor, backColor, type, operator, confidence):
        super(PreSeg_ScrawLabel, self).__init__(pixmap, confmap, origimg, frontColor, backColor, type, operator, confidence)
        self.allowInteract = False
        self.labelClass = 'preseg_scraw'

class RectCut(RectLabel):
    def __init__(self, rect, pRect, cRect, frontColor, backColor, type, operator, confidence):
        super(RectLabel, self).__init__(pRect, cRect, frontColor, backColor, type, operator, confidence)
        self.rect = rect
        self.updateColor()
        self.labelClass = "RectCut"
        self.drawText = False
        print(rect.isEmpty())
        if rect.isEmpty():
            self.creating = True
        # self.setFlag(QGraphicsObject.ItemIsMovable)
        self.srcPos = self.rect.topLeft()

    def mouseReleaseEvent(self, event) -> None:
        if not self.allowInteract:
            return
        # print("release:"+str(event.pos()))
        # print(str(self.rect))
        
        self.adjustPoint = False
        self.adjustBorder = False
        self.adjustAll = False
        self.MouseInLabelSg.emit(False)
        # self.needSaveItem.emit(True)
        # self.selectedItem.emit(self)
        if self.creating == False:
            self.drawText = False
        if self.moveSrcPoints and self.moved:
            self.moveDstPoints = self.getPoints()
            self.posChanged.emit(self.moveSrcPoints, self.moveDstPoints)
        self.moveSrcPoints = None
        self.moveDstPoints = None
        self.moved = False
        self.update()

# 标尺标注和其他标注不同，它不被视为label，只是为了绘制后用于统计实际尺寸
class RulerLabel(QGraphicsObject):
    rulerCreatingSuccess = pyqtSignal(float)
    creatingFailed = pyqtSignal()
    MovingDone = pyqtSignal()
    def __init__(self, pRect, cRect):
        super(RulerLabel, self).__init__()
        self.scale = 1.0
        self.pixLen = 0.0
        self.startPoint = QPointF()
        self.endPoint = QPointF()
        self.setAcceptHoverEvents(True)

        # 矩形范围内端点控制
        self.pRect = pRect # 矩形区域内绘制
        self.cRect = cRect # 矩形区域内控制位置

        self.labelClass = "Ruler"
        self.creating = True

    def pointNormalized(self, point: QPointF):
        x, y = 0, 0
        if point.x() < self.cRect.left():
            x = self.cRect.left()
        elif point.x() > self.cRect.right():
            x = self.cRect.right()
        else:
            x = point.x()
        if point.y() < self.cRect.top():
            y = self.cRect.top()
        elif point.y() > self.cRect.bottom():
            y = self.cRect.bottom()
        else:
            y = point.y()
        return QPointF(x, y)

    def boundingRect(self) -> QRectF:
        """
        用于告知graphicsView如何绘制的区域，需要包含自身
        @return:
        """
        return self.paintRect()

    def paintRect(self):
        """
        计算绘制范围的矩形大小
        @return:
        """
        return self.pRect

    def setScale(self, scale: float) -> None:
        self.scale = scale

    def paint(self, painter, option, widget):
        painter.setPen(QPen(QColor("#6397ef"), 2))
        painter.setBrush(QBrush(QColor("#6397ef"), Qt.SolidPattern))
        painter.setRenderHint(QPainter.Antialiasing)

        if not self.startPoint.isNull() and not self.endPoint.isNull():
            # 绘制直线
            painter.drawLine(self.startPoint * self.scale, self.endPoint * self.scale)

            # 计算中心、长度
            midPoint = (self.startPoint + self.endPoint) * self.scale / 2
            dx = self.endPoint.x() - self.startPoint.x()
            dy = self.endPoint.y() - self.startPoint.y()

            # 绘制起点和终点的垂直线
            angle = math.atan2(dy, dx)
            perpAngle = angle + math.pi / 2
            startPerpStart = self.startPoint * self.scale + QPointF(5 * math.cos(perpAngle), 5 * math.sin(perpAngle))
            startPerpEnd = self.startPoint * self.scale + QPointF(-5 * math.cos(perpAngle), -5 * math.sin(perpAngle))
            painter.drawLine(startPerpStart, startPerpEnd)
            endPerpStart = self.endPoint * self.scale + QPointF(5 * math.cos(perpAngle), 5 * math.sin(perpAngle))
            endPerpEnd = self.endPoint * self.scale + QPointF(-5 * math.cos(perpAngle), -5 * math.sin(perpAngle))
            painter.drawLine(endPerpStart, endPerpEnd)

            # 绘制文本
            if math.degrees(angle) > 90:
                angle = -(180 - math.degrees(angle))
            elif math.degrees(angle) < -90:
                angle = -(180 - math.degrees(angle))
            else:
                angle = math.degrees(angle)
            painter.save()
            painter.translate(midPoint)
            painter.rotate(angle)

            # 设置字体
            font = QFont()
            font.setPixelSize(12)
            painter.setFont(font)

            # 计算文本大小
            text = f"像素长度:{self.pixLen}px"
            fm = QFontMetrics(font)
            textWidth = fm.width(text)
            textHeight = fm.height()

            # 绘制文本背景框
            padding = 5
            textRect = QRectF(-textWidth / 2 - padding, -textHeight - 3 * padding, textWidth + 2 * padding,
                              textHeight + 2 * padding)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor("#6397ef"), Qt.SolidPattern))
            painter.drawRect(textRect)

            # 绘制文本
            painter.setPen(QPen(QColor("white"), 2))
            painter.drawText(textRect, Qt.AlignCenter, text)
            painter.restore()

    def mousePressEvent(self, event) -> None:
        if self.creating:
            if event.button() == Qt.LeftButton:
                if self.startPoint.isNull():
                    self.startPoint = self.pointNormalized(event.pos() / self.scale)
                    self.endPoint = self.startPoint
                    self.update()
                else:
                    self.endPoint = self.pointNormalized(event.pos() / self.scale)
                    self.creating = False
                    self.update()
                    self.rulerCreatingSuccess.emit(self.pixLen)
                    self.MovingDone.emit()

    def mouseMoveEvent(self, event) -> None:
        if self.creating:
            if not self.startPoint.isNull():
                self.endPoint = self.pointNormalized(event.pos() / self.scale)
                # 计算像素长度
                xLen = abs(self.startPoint.x() - self.endPoint.x())
                yLen = abs(self.startPoint.y() - self.endPoint.y())
                self.pixLen = round(float(math.sqrt(xLen * xLen + yLen * yLen)), 2)
                self.update()

    def hoverMoveEvent(self, event: 'QGraphicsSceneHoverEvent') -> None:
        if self.creating:
            if not self.startPoint.isNull():
                self.endPoint = self.pointNormalized(event.pos() / self.scale)
                # 计算像素长度
                xLen = abs(self.startPoint.x() - self.endPoint.x())
                yLen = abs(self.startPoint.y() - self.endPoint.y())
                self.pixLen = round(float(math.sqrt(xLen * xLen + yLen * yLen)), 2)
                self.update()

    def mouseReleaseEvent(self, event) -> None:
        pass

class IntelligentScissors(Label):
    def __init__(self, polygon, prectl, nexctl, pRect, cRect, frontColor, backColor, type, operator, confidence):
        super(IntelligentScissors, self).__init__(pRect, cRect, frontColor, backColor, type, operator, confidence)
        self.polygon = polygon
        self.prectl = prectl if prectl else QPolygonF(polygon)
        self.nexctl = nexctl if nexctl else QPolygonF(polygon)

        self.basePoint = self.polygon.value(0)
        self.lastPoint = self.polygon.value(0)  # 指向绘制过程中最后一个鼠标悬浮点
        self.selected_index = None
        self.moving_all = False

        # self.diameter = 20
        self.addCtl = False
        self.doubleClicked = False
        self.labelClass = "PolygonCurve"
        self.updateColor()
        if self.polygon.count() <= 1:
            self.creating = True
            self.pointNum = 0
        # 增量修改关键点
        self.modifing = False
        self.modified_list = []
        self.modified_plg = []
        self.modified_pre = []
        self.modified_nxt = []
        self.modified_num = 0
        self.events = []

        self.penWidth = 1
        self.diameter = 3  # 端点直径
        self.s_diameter = 18  # 选中时端点直径
        self.h_diameter = 24  # 悬浮时端点直径

    def shape(self):
        """
        shape可以比boundingrect更为复杂
        @return:
        """
        temp = QPainterPath()
        temp.setFillRule(Qt.WindingFill)
        if self.creating or self.modifing and self.modified_num != 0:
            t_rect = self.polygon.boundingRect()
            temp.addRect(self.paintRect())

        else:
            polygon, prectl, nexctl = [], [], []
            for i in range(len(self.polygon)):
                polygon.append(self.polygon.value(i))
                prectl.append(self.prectl.value(i))
                nexctl.append(self.nexctl.value(i))

            if not self.clockwise(polygon): # Qt.WindingFill 与逆时针的多边形不兼容
                polygon.reverse()
                prectl.reverse()
                nexctl.reverse()
                prectl, nexctl = nexctl, prectl
            polygon = QPolygonF(polygon)
            prectl = QPolygonF(prectl)
            nexctl = QPolygonF(nexctl)

            temp.addPath(self.bezierPath(polygon, prectl, nexctl, True, self.scale))

            if self.isSelected():
                for i in range(len(self.polygon)):
                    if i == self.focusedPointIndex:
                        temp.addEllipse(self.polygon.value(i) * self.scale, self.s_diameter / 2, self.s_diameter / 2)
                    elif i == self.hoverPointIndex:
                        temp.addEllipse(self.polygon.value(i) * self.scale, self.h_diameter / 2, self.h_diameter / 2)
                    else:
                        temp.addEllipse(self.polygon.value(i) * self.scale, self.diameter / 2, self.diameter / 2)# self.diameter
                focusedPoint, ctlPoints = self.ctlPoints()
                for point in ctlPoints:
                    # temp.add(QLineF(point, focusedPoint))
                    temp.addEllipse(point, self.diameter / 2, self.diameter / 2)# self.diameter
            if self.drawText:
                temp.addRect(self.textZone()[0])
        return temp
    def textZone(self):
        """
        用于计算信息区域的显示范围
        @return:
        """
        if self.textWidth == None:
            self.textWidth = self.font.pixelSize() * 4
        for i in range(len(self.polygon)):
            if i == 0:
                textPoint = self.polygon.value(i)
            elif textPoint.y() > self.polygon.value(i).y():
                textPoint = self.polygon.value(i)
        rect1, rect2, rect3, rect4 = self.textRect(textPoint.x() * self.scale, textPoint.y() * self.scale)
        return rect1, rect2, rect3, rect4
    def bezierPath(self, polygon, prectl, nexctl, closed, scale=1):
        tpath = QPainterPath()
        tpath.setFillRule(Qt.WindingFill)
        for i in range(len(polygon)):
            if i == 0:
                tpath.moveTo(polygon.value(0) * scale)
            else:
                tpath.cubicTo(nexctl.value(i - 1) * scale, prectl.value(i) * scale, polygon.value(i) * scale)
        if closed:
            # tpath.closeSubpath()
            tpath.cubicTo(nexctl.value(len(nexctl) - 1) * scale, prectl.value(0) * scale, polygon.value(0) * scale)
        return tpath
    def clockwise(self, points_list):
        n = len(points_list)
        if n < 3:
            return 0.0
        area = 0
        for i in range(n):
            x = points_list[i].x()
            y = points_list[i].y()
            area += x * points_list[(i + 1) % n].y() - y * points_list[(i + 1) % n].x()
        return True if area > 0 else False
    def drawBezierPolyline(self, painter):
        painter.drawPath(self.bezierPath(self.polygon, self.prectl, self.nexctl, False, self.scale))
    def drawBezierPolygon(self, painter):
        painter.drawPath(self.bezierPath(self.polygon, self.prectl, self.nexctl, True, self.scale))
    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.Antialiasing)
        # 画蒙版与线
        if self.creating:
            # painter.drawPolyline(QPolygonF(temp_point_list))
            painter.setPen(Qt.NoPen)
            painter.setBrush(self.selectBrush)
            self.drawBezierPolygon(painter)

            painter.setPen(self.selectPen)
            painter.setBrush(Qt.NoBrush)
            self.drawBezierPolyline(painter)
        else:
            painter.setPen(self.selectPen)
            painter.setBrush(self.selectBrush)
            self.drawBezierPolygon(painter)

        # 如果被选中就绘制每个点的圆圈
        # if self.focused:
        if self.isSelected():
            painter.setPen(Qt.NoPen)
            painter.setBrush(self.labelBrush)

            # 锚点
            temp_point_list = []
            for i in range(len(self.polygon)):
                temp_point_list.append(self.polygon.value(i) * self.scale)
            count = 0
            for point in temp_point_list:
                # if count == self.focusedPointIndex:
                #     painter.setPen(Qt.NoPen)
                #     painter.setBrush(QBrush(QColor(0, 0, 0)))
                if count == 0 and self.creating:
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(QBrush(QColor(255, 255, 255)))
                    painter.drawEllipse(point, self.s_diameter / 2, self.s_diameter / 2)
                elif count == self.pointNum-1 and self.creating:
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(QBrush(QColor(255, 255, 255)))
                    painter.drawEllipse(point, self.s_diameter / 2, self.s_diameter / 2)
                else:
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(self.labelBrush)

                if count == self.focusedPointIndex:
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(QColor(255, 255, 255))
                    painter.drawEllipse(point, self.s_diameter / 2, self.s_diameter / 2)
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(self.labelBrush)
                    painter.drawEllipse(point, self.s_diameter / 2 * 0.66, self.s_diameter / 2 * 0.66)    # focused的点扩大1.5倍,并且凸显中心点
                elif count == self.hoverPointIndex and self.creating==True and count==0:#回到初始点放大
                    painter.drawEllipse(point, self.h_diameter / 2, self.h_diameter / 2)    # hover的点扩大1.5倍
                elif count == self.hoverPointIndex and self.creating==False:
                    painter.drawEllipse(point, self.h_diameter / 2, self.h_diameter / 2)    # hover的点扩大1.5倍
                else:
                    painter.drawEllipse(point, self.diameter / 2, self.diameter / 2)
                count += 1

            # 控制点 控制线
            focusedPoint, ctlPoints = self.ctlPoints()
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255))
            for point in ctlPoints:
                painter.drawEllipse(point, 12 / 2, 12 / 2)#self.diameter

            painter.setPen(self.dotPen)
            painter.setBrush(Qt.NoBrush)
            for point in ctlPoints:
                painter.drawLine(QLineF(point, focusedPoint))

        # 画虚线
        # if self.focused or self.creating:
        if self.isSelected() or self.creating:
            painter.setPen(self.dotPen)
            painter.setBrush(Qt.NoBrush)
            self.drawBezierPolygon(painter)

        # 画增量修改
        if self.modifing and self.modified_num != 0:
            # 线
            painter.setPen(self.selectPen)
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(self.bezierPath(QPolygonF(self.modified_plg), QPolygonF(self.modified_pre), QPolygonF(self.modified_nxt), False, self.scale))
            # 蒙版
            painter.setPen(Qt.NoPen)
            painter.setBrush(self.selectBrush)
            painter.drawPath(self.bezierPath(QPolygonF(self.modified_plg), QPolygonF(self.modified_pre), QPolygonF(self.modified_nxt), False, self.scale))
            # 控制点、线
            focusedPoint = self.modified_plg[self.modified_num - 1]
            ctlPoints = [self.modified_pre[self.modified_num - 1], self.modified_nxt[self.modified_num - 1]]
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255))
            for point in ctlPoints:
                painter.drawEllipse(point * self.scale, self.diameter / 2, self.diameter / 2)

            painter.setPen(self.dotPen)
            painter.setBrush(Qt.NoBrush)
            for point in ctlPoints:
                painter.drawLine(QLineF(point * self.scale, focusedPoint * self.scale))

        if self.drawText:
            painter.setPen(self.textPen)
            painter.setFont(self.font)
            self.textWidth = painter.fontMetrics().boundingRect(self.text()).width()

            # painter.setPen(self.labelPen)
            # painter.setBrush(self.labelBrush)
            # painter.drawRect(self.textZone())

            # painter.setPen(self.textPen)
            # painter.setFont(self.font)
            # painter.drawText(self.textZone(), Qt.AlignCenter, self.text())
            rect1, rect2, rect3, rect4 = self.textZone()
            painter.setPen(self.labelPen1)
            painter.setBrush(self.labelBrush1)
            painter.drawRect(rect1)

            painter.setPen(self.labelPen2)
            painter.setBrush(self.labelBrush2)
            painter.drawRect(rect2)

            painter.setPen(self.labelPen1)
            painter.setBrush(self.labelBrush1)
            painter.drawRect(rect3)

            painter.setPen(self.textPen)
            painter.setFont(self.font)
            painter.drawText(rect4, Qt.AlignCenter, self.text())

    def update(self):
        super(IntelligentScissors, self).update()

        polygon_, prectl_, nexctl_ = [], [], []
        for i in range(len(self.polygon)):
            polygon_.append(self.polygon.value(i))
            prectl_.append(self.prectl.value(i))
            nexctl_.append(self.nexctl.value(i))

        reversed = False
        path = QPainterPath()
        if not self.clockwise(polygon_):  # Qt.WindingFill 与逆时针的多边形不兼容
            polygon_.reverse()
            prectl_.reverse()
            nexctl_.reverse()
            prectl_, nexctl_ = nexctl_, prectl_
            reversed = True
        polygon = QPolygonF(polygon_)
        prectl = QPolygonF(prectl_)
        nexctl = QPolygonF(nexctl_)

        subpath_list = []
        for i in range(len(polygon)):
            tpath = QPainterPath()
            if i == 0:
                pass
            else:
                tpath.moveTo(polygon.value(i - 1) * self.scale)
                tpath.cubicTo(nexctl.value(i - 1) * self.scale, prectl.value(i) * self.scale,
                              polygon.value(i) * self.scale)
                subpath_list.append(tpath)
        tpath = QPainterPath()
        tpath.moveTo(polygon.value(len(nexctl) - 1) * self.scale)
        tpath.cubicTo(nexctl.value(len(nexctl) - 1) * self.scale, prectl.value(0) * self.scale,
                      polygon.value(0) * self.scale)
        subpath_list.append(tpath)

        self.subpath_list = subpath_list
    def ctlPoints(self):
        focusedPoint = None
        ctlPoints = []
        if self.focusedPointIndex != -1:

            index = self.focusedPointIndex
            focusedPoint = self.polygon.value(index) * self.scale
            if self.prectl.value(index) != focusedPoint:
                ctlPoints.append(self.prectl.value(index) * self.scale)
            if self.nexctl.value(index) != focusedPoint:
                ctlPoints.append(self.nexctl.value(index) * self.scale)

        return focusedPoint, ctlPoints
    def hoverEnterEvent(self, event: 'QGraphicsSceneHoverEvent') -> None:
        if not self.allowInteract:
            return
        super(IntelligentScissors, self).hoverEnterEvent(event)

    def hoverMoveEvent(self, event: 'QGraphicsSceneHoverEvent') -> None:
        if not self.allowInteract:
            return
        super(IntelligentScissors, self).hoverMoveEvent(event)
        if self.creating:

            self.prepareGeometryChange()
            self.hoverPointIndex = None
            for i in range(len(self.polygon) - 1):
                t_point = self.polygon.value(i) * self.scale
                t_dist = (event.pos().x() - t_point.x()) ** 2 + (event.pos().y() - t_point.y()) ** 2
                if self.hoverPointIndex == i:
                    diameter = self.h_diameter
                else:
                    diameter = 12# self.diameter
                if t_dist <= (diameter / 2) ** 2:
                    self.hoverPointIndex = i
                    break
            while len(self.polygon) > self.pointNum:
                # print('pop ', len(self.polygon) - 1)
                self.polygon.remove(len(self.polygon) - 1)
                self.prectl.remove(len(self.prectl) - 1)
                self.nexctl.remove(len(self.nexctl) - 1)

            # hover到初始点的时候不用增加新点
            if self.hoverPointIndex != 0 or len(self.polygon) == 0:
                newPoint = self.pointNormalized(QPointF(event.pos()) / self.scale)
                self.polygon.append(newPoint)
                self.prectl.append(newPoint)
                self.nexctl.append(newPoint)

            self.update()
        # elif self.focused and self.allowMove:
        elif self.isSelected() and self.allowMove:
            # self.initCursor()
            if self.modifing == True and self.modified_num != 0:
                while len(self.modified_plg) > self.modified_num:
                    self.modified_plg.pop()
                    self.modified_pre.pop()
                    self.modified_nxt.pop()
                if self.hoverPointIndex is None:
                    newPoint = self.pointNormalized(QPointF(event.pos()) / self.scale)
                    self.modified_plg.append(newPoint)
                    self.modified_pre.append(newPoint)
                    self.modified_nxt.append(newPoint)
                else:
                    self.modified_plg.append(self.polygon.value(self.hoverPointIndex))
                    self.modified_pre.append(self.polygon.value(self.hoverPointIndex))
                    self.modified_nxt.append(self.polygon.value(self.hoverPointIndex))
            # 如果鼠标悬停于边缘，则暂时按扩展边缘点的鼠标手势，否则为整体移动的手势

            polygon_, prectl_, nexctl_ = [], [], []
            for i in range(len(self.polygon)):
                polygon_.append(self.polygon.value(i))
                prectl_.append(self.prectl.value(i))
                nexctl_.append(self.nexctl.value(i))

            reversed = False
            path = QPainterPath()
            if not self.clockwise(polygon_):  # Qt.WindingFill 与逆时针的多边形不兼容
                polygon_.reverse()
                prectl_.reverse()
                nexctl_.reverse()
                prectl_, nexctl_ = nexctl_, prectl_
                reversed = True
            polygon = QPolygonF(polygon_)
            prectl = QPolygonF(prectl_)
            nexctl = QPolygonF(nexctl_)

            # subpath_list = []
            # for i in range(len(polygon)):
            #     tpath = QPainterPath()
            #     if i == 0:
            #         pass
            #     else:
            #         tpath.moveTo(polygon.value(i - 1) * self.scale)
            #         tpath.cubicTo(nexctl.value(i - 1) * self.scale, prectl.value(i) * self.scale, polygon.value(i) * self.scale)
            #         subpath_list.append(tpath)
            # tpath = QPainterPath()
            # tpath.moveTo(polygon.value(len(nexctl) - 1) * self.scale)
            # tpath.cubicTo(nexctl.value(len(nexctl) - 1) * self.scale, prectl.value(0) * self.scale, polygon.value(0) * self.scale)
            # subpath_list.append(tpath)

            ## 二分近似查找鼠标点击边缘处的坐标
            for i, path in enumerate(self.subpath_list):
                t, find = self.findNearPoint(path, event.pos())
                if find == True:
                    #print("2")
                    pixmap = QPixmap(":/resources/添加节点.png")  # pixmap 是 QPixmap()的实例化，QPixmap()类用于图片的显示
                    new_pixmap = pixmap.scaled(16, 16)  # scaled方法返回自定义尺寸的副本
                    cursor = QCursor(new_pixmap, 0, 0)
                    break
                else:
                    #print("1")
                    cursor = Qt.SizeAllCursor
            flag = False
            for i in range(len(self.polygon)):
                t_point = self.polygon.value(i) * self.scale
                t_dist = (event.pos().x() - t_point.x()) ** 2 + (event.pos().y() - t_point.y()) ** 2
                if self.focusedPointIndex == i:
                    diameter = self.s_diameter
                elif self.hoverPointIndex == i:
                    diameter = self.h_diameter
                else:
                    diameter = self.diameter
                if t_dist <= (diameter / 2 + 2) ** 2:
                    self.hoverPointIndex = i
                    flag = True
                    if self.addCtl:
                        pixmap = QPixmap(":/resources/添加控制点.png")  # pixmap 是 QPixmap()的实例化，QPixmap()类用于图片的显示
                        new_pixmap = pixmap.scaled(16, 16)  # scaled方法返回自定义尺寸的副本
                        cursor = QCursor(new_pixmap, 0, 0)
                    else:
                        if i == 0:
                            a = self.polygon.value(len(self.polygon) - 1)
                            b = self.polygon.value(i)
                            c = self.polygon.value(i + 1)
                        elif i == len(self.polygon) - 1:
                            a = self.polygon.value(i - 1)
                            b = self.polygon.value(i)
                            c = self.polygon.value(0)
                        else:
                            a = self.polygon.value(i - 1)
                            b = self.polygon.value(i)
                            c = self.polygon.value(i + 1)
                        cursor = self.angle2Cursor(a, b, c)
                    break

            if not flag:
                self.hoverPointIndex = None

            self.setCursor(cursor)
            self.update()

    def angle2Cursor(self, A, B, C):

        def clockwise_angle(v1, v2):
            x1, y1 = v1
            x2, y2 = v2
            dot = x1 * x2 + y1 * y2
            det = x1 * y2 - y1 * x2
            theta = np.arctan2(det, dot)
            theta = theta if theta > 0 else 2 * np.pi + theta
            return np.degrees(theta)

        a = np.array((A.x(), A.y()))
        b = np.array((B.x(), B.y()))
        c = np.array((C.x(), C.y()))
        avec = a - b
        bvec = np.array((100, 0))
        cvec = c - b
        a1 = clockwise_angle(avec, bvec)
        a2 = clockwise_angle(cvec, bvec)
        a = (a1 + a2) / 2 % 180
        if -22.5 < a <= 22.5 or 157.5 < a <= 180:
            cursor = Qt.SizeHorCursor
        elif 22.5 < a <= 67.5:
            cursor = Qt.SizeBDiagCursor
        elif 67.5 < a <= 112.5:
            cursor = Qt.SizeVerCursor
        elif 112.5 < a <= 157.5:
            cursor = Qt.SizeFDiagCursor
        return cursor

    def hoverLeaveEvent(self, event: 'QGraphicsSceneHoverEvent') -> None:
        if not self.allowInteract:
            return
        super(IntelligentScissors, self).hoverLeaveEvent(event)
        # self.setCursor(Qt.OpenHandCursor)
        self.unsetCursor()
        self.hoverPointIndex = None
        self.update()
        # print("hover leave")
        pass

    def selectedPointIndex(self, x, y):
        # 判断鼠标点击的具体位置
        dist_index = -1
        min_dist = 10000000
        for i in range(len(self.polygon)):
            t_point = self.polygon.value(i) * self.scale
            t_dist = (x - t_point.x()) ** 2 + (y - t_point.y()) ** 2
            if i == self.hoverPointIndex:
                diameter = self.h_diameter
            elif i == self.focusedPointIndex:
                diameter = self.s_diameter
            else:
                diameter = self.diameter
            if t_dist <= (diameter / 2 + 2) ** 2 and t_dist < min_dist:
                dist_index = i
                min_dist = t_dist
        return dist_index

    def mousePressEvent(self, event) -> None:
        if not self.allowInteract:
            return
        # self.focused = True
        # self.setSelected(True)
        self.selectedItem.emit(self)
        # super().mousePressEvent(event)
        #print(self.focusedPointIndex)  # 保持len-1#我让它一直为0
        #print(self.ctlPointIndex)  # 保持-1
        if self.creating:
            if event.buttons() & Qt.RightButton:
                self.rightClicked = True
            else:
                self.rightClicked = False
            # elif self.lastPoint != None:
            if self.hoverPointIndex == 0:
                if len(self.polygon) < 2:
                    self.Die = True
                    self.hide()
                    self.setInteract(False)
                else:
                    self.creatingSuccess.emit(self.type, self.labelClass)
                self.creating = False
                self.drawText = True
                self.update()
                self.creatingFinish.emit(self)
                self.focusedPointIndex = 0
                self.allowMove = True
                # event.accept()
            elif self.rightClicked == False:
                # self.polygon.remove(len(self.polygon) - 1)
                # self.polygon.append(event.pos() / self.scale)
                self.lastPoint = None
                self.pointNum += 1
                self.focusedPointIndex = self.pointNum-1

        else:
            self.moveSrcPoints = self.getPoints()  # 记录修改之前状态

            tPos = event.pos()
            x = tPos.x()
            y = tPos.y()

            if self.focusedPointIndex != -1:  # 初始化选中的锚点
                index = self.focusedPointIndex
                t_point1, t_point2, t_point3 = self.prectl.value(index) * self.scale, self.nexctl.value(
                    index) * self.scale, self.polygon.value(index) * self.scale
                t_dist1 = (event.pos().x() - t_point1.x()) ** 2 + (event.pos().y() - t_point1.y()) ** 2
                t_dist2 = (event.pos().x() - t_point2.x()) ** 2 + (event.pos().y() - t_point2.y()) ** 2
                t_dist3 = (event.pos().x() - t_point3.x()) ** 2 + (event.pos().y() - t_point3.y()) ** 2
                if t_dist1 > (self.diameter / 2 + 2) ** 2 and t_dist2 > (
                        self.diameter / 2 + 2) ** 2 and self.modifing == False:
                    # if t_dist1 > (self.diameter / 2) ** 2 and t_dist2 > (self.diameter / 2) ** 2 and self.modifing == False:
                    self.focusedPointIndex = -1
                    self.ctlPointIndex = -1
            if event.buttons() & Qt.LeftButton or event.buttons() & Qt.RightButton:
                dist_index = self.selectedPointIndex(x, y)
                if dist_index != -1:  # 点击了锚点
                    self.selected_index = dist_index
                    self.setCursor(Qt.CrossCursor)

                    for i in range(len(self.polygon)):
                        t_point = self.polygon.value(i) * self.scale
                        t_dist = (event.pos().x() - t_point.x()) ** 2 + (event.pos().y() - t_point.y()) ** 2
                        if t_dist <= (self.diameter / 2 + 2) ** 2:
                            self.focusedPointIndex = i
                            break
                    if self.modifing == True:
                        if len(self.modified_plg) == 0:  # 增量修改入口
                            self.modified_plg.append(self.polygon.value(i))
                            self.modified_pre.append(self.polygon.value(i))
                            self.modified_nxt.append(self.polygon.value(i))
                            self.modified_num += 1
                            self.drawText = False
                        else:  # 增量修改结束
                            begin = self.modified_plg[0]
                            end = self.modified_plg[-1]
                            t_plg, n_plg = [], []
                            t_pre, n_pre = [], []
                            t_nxt, n_nxt = [], []
                            for i in range(len(self.polygon)):
                                t_plg.append(self.polygon.value(i))
                                t_pre.append(self.prectl.value(i))
                                t_nxt.append(self.nexctl.value(i))
                                if self.polygon.value(i) == begin:
                                    begin_i = i
                                if self.polygon.value(i) == end:
                                    end_i = i
                            right = True if (end_i - begin_i) % len(t_plg) <= len(t_plg) - (end_i - begin_i) % len(
                                t_plg) else False
                            if not right:
                                begin_i, end_i = end_i, begin_i
                                self.modified_plg.reverse()
                                self.modified_pre.reverse()
                                self.modified_nxt.reverse()
                            i = 0
                            if begin_i < end_i:
                                n_plg += t_plg[0:begin_i]
                                n_plg += self.modified_plg
                                n_pre += t_pre[0:begin_i]
                                n_pre += self.modified_pre
                                n_nxt += t_nxt[0:begin_i]
                                n_nxt += self.modified_nxt
                                if end_i + 1 < len(t_plg):
                                    n_plg += t_plg[end_i + 1:]
                                    n_pre += t_pre[end_i + 1:]
                                    n_nxt += t_nxt[end_i + 1:]
                            elif begin_i > end_i:
                                n_plg += self.modified_plg
                                n_plg += t_plg[end_i + 1:begin_i]
                                n_pre += self.modified_pre
                                n_pre += t_pre[end_i + 1:begin_i]
                                n_nxt += self.modified_nxt
                                n_nxt += t_nxt[end_i + 1:begin_i]
                            if n_plg:
                                self.polygon = QPolygonF(n_plg)
                                self.prectl = QPolygonF(n_pre)
                                self.nexctl = QPolygonF(n_nxt)
                            self.clearModify()
                            self.modifing = False
                            self.drawText = True
                            self.update()
                elif self.modifing and self.modified_num != 0:  # 选中会掩盖增量修改
                    self.modified_num += 1
                elif self.focusedPointIndex != -1:  # 点击了控制点
                    if t_dist1 <= (12 / 2 + 2) ** 2:#12为正常的label的self.diameter
                        self.ctlPointIndex = 0
                    elif t_dist2 <= (12 / 2 + 2) ** 2:
                        self.ctlPointIndex = 1
                else:  # 点击内部点
                    self.moving_all = True
                    self.selected_index = None

    def clearModify(self):
        self.modified_plg.clear()
        self.modified_pre.clear()
        self.modified_nxt.clear()
        self.modified_num = 0

    def findNearPoint(self, path, pos):
        # 二分近似查找鼠标点击边缘处的坐标
        x, y = 0, 1
        max_d = 65535
        count = 0
        find = True
        t = 0
        while max_d > self.penWidth:
            # 二分查找次数设置上限，否则会卡死
            if count >= 10:
                find = False
                break
            m = (x + y) / 2
            m1 = (x + m) / 2
            m2 = (y + m) / 2

            t1 = path.pointAtPercent(m1)
            t2 = path.pointAtPercent(m2)

            l1 = euclideanDistance(t1, pos)
            l2 = euclideanDistance(t2, pos)

            if l1 < l2:
                y = m
                t = m
            else:
                x = m
                t = m
            max_d = max(l1, l2)
            count += 1
        return t, find

    def mouseDoubleClickEvent(self, event: 'QGraphicsSceneMouseEvent') -> None:
        if not self.allowInteract:
            return
        if self.creating:
            if len(self.polygon) < 5:
                self.Die = True
                self.hide()
                self.setInteract(False)
            else:
                self.polygon.remove(len(self.polygon) - 1)
                self.prectl.remove(len(self.prectl) - 1)
                self.nexctl.remove(len(self.nexctl) - 1)
                self.polygon.remove(len(self.polygon) - 1)
                self.prectl.remove(len(self.prectl) - 1)
                self.nexctl.remove(len(self.nexctl) - 1)
                self.creatingSuccess.emit(self.type, self.labelClass)

            self.creating = False
            self.drawText = True
            self.allowMove = True
            self.update()
            self.creatingFinish.emit(self)
        else:
            # 双击增加点
            localPos = event.pos()
            polygon_, prectl_, nexctl_ = [], [], []
            for i in range(len(self.polygon)):
                polygon_.append(self.polygon.value(i))
                prectl_.append(self.prectl.value(i))
                nexctl_.append(self.nexctl.value(i))

            reversed = False
            path = QPainterPath()
            if not self.clockwise(polygon_):  # Qt.WindingFill 与逆时针的多边形不兼容
                polygon_.reverse()
                prectl_.reverse()
                nexctl_.reverse()
                prectl_, nexctl_ = nexctl_, prectl_
                reversed = True
            polygon = QPolygonF(polygon_)
            prectl = QPolygonF(prectl_)
            nexctl = QPolygonF(nexctl_)

            # path.addPath(self.bezierPath(polygon, prectl, nexctl, True))
            # path = self.painterPath

            # subpath_list = []
            # for i in range(len(polygon)):
            #     tpath = QPainterPath()
            #     if i == 0:
            #         pass
            #     else:
            #         tpath.moveTo(polygon.value(i - 1) * self.scale)
            #         tpath.cubicTo(nexctl.value(i - 1) * self.scale, prectl.value(i) * self.scale, polygon.value(i) * self.scale)
            #         subpath_list.append(tpath)
            # tpath = QPainterPath()
            # tpath.moveTo(polygon.value(len(nexctl) - 1) * self.scale)
            # tpath.cubicTo(nexctl.value(len(nexctl) - 1) * self.scale, prectl.value(0) * self.scale, polygon.value(0) * self.scale)
            # subpath_list.append(tpath)

            # print(path.pointAtPercent(0))
            # print(path.pointAtPercent(1))

            for i, path in enumerate(self.subpath_list):
                t, find = self.findNearPoint(path, localPos)

                if find == True:
                    self.moveSrcPoints = self.getPoints()
                    # length = 0
                    # for i, tpath in enumerate(subpath_list):
                    #     length += tpath.length()
                    #     percent = length / path.length()
                    #     if percent > t:
                    #         break
                    polygon_.insert(i + 1, localPos / self.scale)
                    prectl_.insert(i + 1, localPos / self.scale)
                    nexctl_.insert(i + 1, localPos / self.scale)
                    if reversed:
                        polygon_.reverse()
                        prectl_.reverse()
                        nexctl_.reverse()
                        prectl_, nexctl_ = nexctl_, prectl_

                    self.polygon = QPolygonF(polygon_)
                    self.prectl = QPolygonF(prectl_)
                    self.nexctl = QPolygonF(nexctl_)
                    if not reversed:
                        self.focusedPointIndex = i + 1
                    else:
                        self.focusedPointIndex = len(self.polygon) - i - 2
                    self.doubleClicked = True
                    self.update()
                    self.moveDstPoints = self.getPoints()
                    self.posChanged.emit(self.moveSrcPoints, self.moveDstPoints)
                    self.moveSrcPoints = None
                    print('double click')
                    break

    def mouseMoveEvent(self, event) -> None:
        if not self.allowInteract:
            return
        self.moved = True
        # event.accept()
        # 创建标注或点
        if self.creating or self.addCtl or self.doubleClicked:
            targetIndex = len(self.polygon) - 1 if self.creating else self.focusedPointIndex
            self.nexctl.remove(targetIndex)
            tPoint = event.pos()
            anchorPoint = self.polygon.value(targetIndex) * self.scale
            t_dist = (tPoint.x() - anchorPoint.x()) ** 2 + (tPoint.y() - anchorPoint.y()) ** 2
            if t_dist <= (self.s_diameter / 2 + 2) ** 2:
                tPoint = anchorPoint
            self.nexctl.insert(targetIndex, tPoint / self.scale)
            ox = 2 * self.polygon.value(targetIndex).x() * self.scale - event.pos().x()
            oy = 2 * self.polygon.value(targetIndex).y() * self.scale - event.pos().y()
            othersidePoint = QPointF(ox, oy)
            self.prectl.remove(targetIndex)
            tPoint = othersidePoint
            anchorPoint = self.polygon.value(targetIndex) * self.scale
            t_dist = (tPoint.x() - anchorPoint.x()) ** 2 + (tPoint.y() - anchorPoint.y()) ** 2
            if t_dist <= (self.s_diameter / 2 + 2) ** 2:
                tPoint = anchorPoint
            self.prectl.insert(targetIndex, tPoint / self.scale)
            self.update()
        # 增量添加点
        elif self.modifing and self.modified_num != 0:
            targetIndex = self.modified_num - 1
            self.modified_nxt.pop(targetIndex)
            tPoint = event.pos()
            anchorPoint = self.modified_plg[targetIndex] * self.scale
            t_dist = (tPoint.x() - anchorPoint.x()) ** 2 + (tPoint.y() - anchorPoint.y()) ** 2
            if t_dist <= (self.s_diameter / 2 + 2) ** 2:
                tPoint = anchorPoint
            self.modified_nxt.insert(targetIndex, tPoint / self.scale)
            ox = 2 * self.modified_plg[targetIndex].x() * self.scale - event.pos().x()
            oy = 2 * self.modified_plg[targetIndex].y() * self.scale - event.pos().y()
            othersidePoint = QPointF(ox, oy)
            self.modified_pre.pop(targetIndex)
            tPoint = othersidePoint
            anchorPoint = self.modified_plg[targetIndex] * self.scale
            t_dist = (tPoint.x() - anchorPoint.x()) ** 2 + (tPoint.y() - anchorPoint.y()) ** 2
            if t_dist <= (self.s_diameter / 2 + 2) ** 2:
                tPoint = anchorPoint
            self.modified_pre.insert(targetIndex, tPoint / self.scale)
            self.update()
        # 拖动点的位置
        elif self.selected_index != None and self.ctlPointIndex == -1:
            oldPoint = self.polygon.value(self.selected_index)
            oldPre = self.prectl.value(self.selected_index)
            oldNex = self.nexctl.value(self.selected_index)

            self.polygon.remove(self.selected_index)
            self.prectl.remove(self.selected_index)
            self.nexctl.remove(self.selected_index)

            newPoint = self.pointNormalized(event.pos() / self.scale)
            oPos = newPoint - oldPoint
            newPre = oldPre + oPos
            newNex = oldNex + oPos

            self.polygon.insert(self.selected_index, newPoint)
            self.prectl.insert(self.selected_index, newPre)
            self.nexctl.insert(self.selected_index, newNex)
            self.drawText = False
            self.prepareGeometryChange()
            self.update()
            # 拖动控制点
        elif self.ctlPointIndex != -1:
            index = self.focusedPointIndex
            if self.ctlPointIndex == 0:
                self.prectl.remove(index)
                tPoint = event.pos()
                anchorPoint = self.polygon.value(index) * self.scale
                t_dist = (tPoint.x() - anchorPoint.x()) ** 2 + (tPoint.y() - anchorPoint.y()) ** 2
                if t_dist <= (self.s_diameter / 2 + 2) ** 2:
                    tPoint = anchorPoint
                self.prectl.insert(index, tPoint / self.scale)
            elif self.ctlPointIndex == 1:
                self.nexctl.remove(index)
                tPoint = event.pos()
                anchorPoint = self.polygon.value(index) * self.scale
                t_dist = (tPoint.x() - anchorPoint.x()) ** 2 + (tPoint.y() - anchorPoint.y()) ** 2
                if t_dist <= (self.s_diameter / 2 + 2) ** 2:
                    tPoint = anchorPoint
                self.nexctl.insert(index, tPoint / self.scale)
            self.update()
            # 拖动整体
        elif self.moving_all:
            self.polygon.translate((event.pos() - event.lastPos()) / self.scale)
            self.prectl.translate((event.pos() - event.lastPos()) / self.scale)
            self.nexctl.translate((event.pos() - event.lastPos()) / self.scale)
            self.contourNormalized()
            self.drawText = False
            self.prepareGeometryChange()
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if not self.allowInteract:
            return
        # if not self.creating and self.selected_index != None:
        #     self.selected_index = None
        #     self.drawText = True
        #     self.update()

        if self.moving_all:
            self.moving_all = False
            self.drawText = True
            self.update()
        if self.moveSrcPoints:
            if self.moved or self.doubleClicked:
                self.moveDstPoints = self.getPoints()
                self.posChanged.emit(self.moveSrcPoints, self.moveDstPoints)
        self.moveSrcPoints = None
        self.moveDstPoints = None
        self.doubleClicked = False
        self.moved = False
        self.ctlPointIndex = -1

    def contourNormalized(self):
        polygon, prectl, nexctl = [], [], []
        for i in range(len(self.polygon)):
            polygon.append(self.polygon.value(i))
        ox, oy = self.posOffset(polygon)
        self.polygon.translate(ox, oy)
        self.prectl.translate(ox, oy)
        self.nexctl.translate(ox, oy)

    '''
    description: 删除localpos位置的关键点及控制点
    param {*} self
    param {*} localPos
    return {*}
    '''

    def deleteKeyPoint(self, localPos):
        if len(self.polygon) <= 2:
            return
        pointIndex = self.selectedPointIndex(localPos.x(), localPos.y())
        self.polygon.remove(pointIndex)
        self.prectl.remove(pointIndex)
        self.nexctl.remove(pointIndex)
        self.update()

    def exportPixmap(self):
        t_painter = QPainter()
        pixmap = QPixmap(int(self.cRect.width()), int(self.cRect.height()))
        pixmap.fill(QColor(0, 0, 0))
        t_painter.begin(pixmap)
        t_painter.setPen(Qt.NoPen)
        t_painter.setBrush(self.selectBrush)
        # t_painter.setCompositionMode(QPainter.CompositionMode_Source)
        t_painter.setRenderHint(QPainter.Antialiasing)
        t_painter.drawPath(self.bezierPath(self.polygon, self.prectl, self.nexctl, True))
        t_painter.end()
        return pixmap

    def exportMask(self):
        pixmap = self.exportPixmap()
        mask = lblPixmapToNmp(pixmap, gray=True)

        # mask = np.zeros((int(self.cRect.width()), int(self.cRect.height())), dtype=np.uint8)
        # where = np.where(nmp != (0,0,0))
        # mask[where] = 255
        return mask

    def getExport(self):
        dict = super(IntelligentScissors, self).getExport()
        points1 = []
        for i in range(len(self.polygon)):
            points1.append((self.polygon.value(i).x(), self.polygon.value(i).y()))
        points2 = []
        for i in range(len(self.prectl)):
            points2.append((self.prectl.value(i).x(), self.prectl.value(i).y()))
        points3 = []
        for i in range(len(self.nexctl)):
            points3.append((self.nexctl.value(i).x(), self.nexctl.value(i).y()))
        dict["point_list"] = [points1, points2, points3]

        return dict

    def getPoints(self):
        points1 = []
        for i in range(len(self.polygon)):
            points1.append(self.polygon.value(i))
        points2 = []
        for i in range(len(self.prectl)):
            points2.append(self.prectl.value(i))
        points3 = []
        for i in range(len(self.nexctl)):
            points3.append(self.nexctl.value(i))
        return [points1, points2, points3]

    def setPoints(self, points):
        points1, points2, points3 = points
        self.polygon = QPolygonF(points1)
        self.prectl = QPolygonF(points2)
        self.nexctl = QPolygonF(points3)
        self.update()