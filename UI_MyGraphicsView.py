import math
import numpy as np

from PyQt5.QtWidgets import QGraphicsView, QGraphicsPixmapItem, QGraphicsScene
from PyQt5 import QtGui
from PyQt5.QtGui import QImage, QPixmap, QColor, QPolygonF
from PyQt5.QtCore import Qt, pyqtSignal, QRectF, QPointF
from PIL import ImageQt, Image
import cv2
from wisdom_store.src.utils.image_transform import *
from wisdom_store.src.utils.image_process import *

PI = 3.1415926535

class MyGraphicsView(QGraphicsView):
    needSaveItem = pyqtSignal(bool)
    labelSelect = pyqtSignal(str)
    sizeChanged = pyqtSignal()

    def __init__(self, parent):
        super(MyGraphicsView, self).__init__(parent=parent)
        self.myScene = QGraphicsScene()
        self.setScene(self.myScene)

        self.labelList = []
        self._scale = 1.0
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)

        self.current_select_index = 0

        self.origImg = QPixmap()
        self.brightness = 0.0
        self.contrast = 0.0
        self.saturation = 0.0
        self.gama = 1.0
        # self.flip_mode = False
        self.microImg = QPixmap()


    def getLabelList(self):
        temp = []
        for label in self.labelList:
            if label.Die != True:
                temp.append(label)
        return temp

    def getValidLabelList(self):
        temp = []
        for label in self.labelList:
            if label.Die != True and label.labelClass != 'Feedback':
                temp.append(label)
        return temp

    def microImgRectF(self):
        micrec = QRectF(self.microImg.rect()).normalized()
        # return QRectF(micrec.topLeft() * self._scale, micrec.bottomRight() * self._scale)
        return micrec

    def loadImg(self, path):
        tImg = QImage(path)
        self.bright = 0
        self.contrast = 0
        self.imgArray = np.array(ImageQt.fromqpixmap(tImg))
        self.origImg = QPixmap.fromImage(tImg)
        self.microImg = QPixmap.fromImage(tImg)
        self.microImgItem = QGraphicsPixmapItem(self.microImg)
        self.microImgItem.setScale(self._scale)
        self.myScene.clear()
        self.labelList = []
        self.current_select_index = 0
        self.myScene.addItem(self.microImgItem)
        self.microImgItem.setZValue(-2000)

        return (self.microImg.width(), self.microImg.height())


    def updateBrightContrast(self, bright, contrast):
        '''
        亮度对比度范围为-1~1
        '''
        self.bright = bright
        self.contrast = contrast
        t_img = ImageQt.fromqpixmap(self.origImg)
        t_metrix = np.array(t_img)

        t_metrix = (t_metrix - 127.5 * (1 - self.bright)) * math.tan((45 + 44 * self.contrast) / 180 * PI) + 127.5 * (1 + self.bright)
        t_metrix[t_metrix < 0] = 0
        t_metrix[t_metrix > 255] = 255
        
        img = t_metrix  # numpy类型图片
        img = img.astype("uint8")
        img = QtGui.QImage(img[:], img.shape[1], img.shape[0], img.shape[1] * 3, QtGui.QImage.Format_RGB888)

        self.microImg = QtGui.QPixmap(img)

        self.microImgItem.setPixmap(self.microImg)

    def updateBCS(self, brightness, contrast, saturation):
        newMicroImg = imgPixmapToNmp(self.origImg)
        if brightness is not None:
            self.brightness = brightness
        newMicroImg = changeBrightness(newMicroImg, self.brightness)
        if contrast is not None:
            self.contrast = contrast
        newMicroImg = changeContrast(newMicroImg, self.contrast)
        if saturation is not None:
            self.saturation = saturation
        newMicroImg = changeSaturation(newMicroImg, self.saturation)
        self.microImg = nmpToImgPixmap(newMicroImg)
        # self.microImgItem.setPixmap(self.microImg)

    def resetBCS(self):
        self.brightness = 0.0
        self.contrast = 0.0
        self.saturation = 0.0

    def updateBrightness(self, brightness):
        self.brightness = brightness
        newMicroImg = imgPixmapToNmp(self.microImg)
        newMicroImg = changeBrightness(newMicroImg, self.brightness)
        newMicroImg = changeContrast(newMicroImg, self.contrast)
        newMicroImg = changeSaturation(newMicroImg, self.saturation)
        self.microImg = nmpToImgPixmap(newMicroImg)
        self.microImgItem.setPixmap(self.microImg)

    def updateContrast(self, contrast):
        self.contrast = contrast
        newMicroImg = imgPixmapToNmp(self.microImg)
        newMicroImg = changeBrightness(newMicroImg, self.brightness)
        newMicroImg = changeContrast(newMicroImg, self.contrast)
        newMicroImg = changeSaturation(newMicroImg, self.saturation)
        self.microImg = nmpToImgPixmap(newMicroImg)
        self.microImgItem.setPixmap(self.microImg)

    def updateSaturation(self, saturation):
        self.saturation = saturation
        newMicroImg = imgPixmapToNmp(self.origImg)
        newMicroImg = changeBrightness(newMicroImg, self.brightness)
        newMicroImg = changeContrast(newMicroImg, self.contrast)
        newMicroImg = changeSaturation(newMicroImg, self.saturation)
        self.microImg = nmpToImgPixmap(newMicroImg)
        self.microImgItem.setPixmap(self.microImg)

    def updateReversePhase(self, input_path=None, save_path=None):
        if input_path:
            t_metrix = cv2.imread(input_path)
        else:
            t_img = ImageQt.fromqpixmap(self.microImg)
            t_metrix = np.array(t_img)

        img = 255 - t_metrix  # numpy类型图片
        img = img.astype("uint8")
        qimg = QtGui.QImage(img[:], img.shape[1], img.shape[0], img.shape[1] * 3, QtGui.QImage.Format_RGB888)

        self.microImg = QtGui.QPixmap(qimg)

        if not input_path:
            self.microImgItem.setPixmap(self.microImg)

        # if save_path:
        #     # cv2.imwrite(save_path, img)
        #     cv2.imencode('.jpg', img)[1].tofile(save_path)
        self.saveEnhancedImg(save_path)

    def saveEnhancedImg(self, save_path = None):
        if save_path:
            saveImgNpy = imgPixmapToNmp(self.microImg)
            saveImg = Image.fromarray(saveImgNpy)
            saveImg.save(save_path)
        tImg = QImage(save_path)
        self.origImg = QPixmap.fromImage(tImg)
        
    def temporalLoadRawImage(self, rawImgFile=None):
        if rawImgFile:
            tImg = QImage(rawImgFile)
            tpixmap = QPixmap.fromImage(tImg)
            self.microImgItem.setPixmap(tpixmap)
        else:
            self.microImgItem.setPixmap(self.microImg)

    def saveLabel(self, needSave):
        self.needSaveItem.emit(needSave)

    def selectItem(self, label):
        for i, _label in enumerate(self.labelList):
            # _label.focused = False
            _label.setSelected(False)
            if _label == label:
                self.current_select_index = i
                _label.setSelected(True)
            label.prepareGeometryChange()

        # label.focused = True
        # self.labelSelect.emit(label.type)

    # 允许选中多个
    def selectMoreItem(self, labels):
        for i, _label in enumerate(self.labelList):
            # _label.focused = False
            _label.setSelected(False)
        for label in labels:
            for i, _label in enumerate(self.labelList):
                if _label == label:
                    self.current_select_index = i
                    _label.setSelected(True)
                    label.prepareGeometryChange()
                    break

    def loadLabel(self, t_label):
        self.labelList.append(t_label)
        t_label.setScale(self._scale)
        t_label.updateColor()
        self.myScene.addItem(t_label)
        t_label.needSaveItem.connect(self.saveLabel)
        t_label.selectedItem.connect(self.selectItem)
        # t_label.drawText = True

        return t_label
    def loadLabel_new(self, t_label):
        self.labelList.append(t_label)
        t_label.setScale(self._scale)
        t_label.updateColor()
        self.myScene.addItem(t_label)
        t_label.needSaveItem.connect(self.saveLabel)
        t_label.selectedItem.connect(self.selectItem)
        t_label.creatingFinish.connect(self.remove_label)
        # t_label.drawText = True
        return t_label
    def remove_label(self,t_label):
        self.labelList.remove(t_label)
    def setScale(self, scale):
        for label in self.labelList:
            label.setScale(scale)
            label.prepareGeometryChange()
        self.microImgItem.setScale(scale)
        self._scale = scale
        self.viewport().update()

    def pointNormalized(self, point: QPointF):
        x, y = 0, 0
        cRect = self.microImgRectF()
        if point.x() < cRect.left():
            x = cRect.left()
        elif point.x() > cRect.right():
            x = cRect.right()
        else:
            x = point.x()
        if point.y() < cRect.top():
            y = cRect.top()
        elif point.y() > cRect.bottom():
            y = cRect.bottom()
        else:
            y= point.y()
        return QPointF(x, y)
        
    # def setCursor(self, a0) -> None:
    #     # if self.microImgItem:
    #     #     self.microImgItem.setCursor(a0)
    #     return super().setCursor(a0)

    # def unsetCursor(self) -> None:
    #     if self.microImgItem:
    #         self.microImgItem.unsetCursor()
    #     return super().unsetCursor()
    def imageRotate(self, originpath, angle):
        img = cv2.imread(originpath)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        height, width = img.shape[:2]
        # 计算图像中心点位置
        center = (width / 2, height / 2)

        # 定义旋转矩阵
        rotation_matrix = cv2.getRotationMatrix2D(center, angle, 1.0)

        # 进行仿射变换，得到旋转后的图像
        rotated_image = cv2.warpAffine(img, rotation_matrix, (width, height))
        # plt.imshow(rotated_image)
        # plt.show()
        self.microImg = nmpToImgPixmap(rotated_image)
        self.microImgItem.setPixmap(self.microImg)

    def imageFlip(self, flip_code):
        img = imgPixmapToNmp(self.origImg)
        flipped_img = cv2.flip(img, flip_code)
        self.microImg = nmpToImgPixmap(flipped_img)
        self.microImgItem.setPixmap(self.microImg)