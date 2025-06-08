from PyQt5.QtWidgets import *
from PyQt5.Qt import Qt
from PyQt5 import QtCore, QtGui
from PyQt5.QtCore import pyqtSignal
from wisdom_store.ui.main.Ui_LabelShow import Ui_LabelShow
from wisdom_store.wins import Dialog
from wisdom_store.wins.main_foldingbar_item import FoldingBarItem
import sys
import wisdom_store.ui.main.resources_rc
from wisdom_store.src.sdk.project.project import Project
import copy

class LabelShow(FoldingBarItem):
    AlphaChanged = pyqtSignal(int)
    AlphaSelectChanged = pyqtSignal(int)
    InstanceColorChanged = pyqtSignal(str)

    def __init__(self, parent):
        super(LabelShow, self).__init__()
        self.parent = parent

        # 初始化窗口
        self.win = QWidget()
        self.mainWin = Ui_LabelShow()
        self.mainWin.setupUi(self.win)
        self.set_content(self.win)
        self.set_title("标注展示")

        # 隐藏系统默认框架
        self.setWindowFlags(Qt.FramelessWindowHint)

        # 设置鼠标追踪
        self.setMouseTracking(True)

        # 初始化实例颜色下拉框
        self.mainWin.comboBoxInstanceColor.clear()
        self.mainWin.comboBoxInstanceColor.addItem("与类型一致")
        self.mainWin.comboBoxInstanceColor.addItem("随机设置")

        # 事件绑定
        self.signalConnect()

        # 控件状态初始化
        self.stateInit()

    def signalConnect(self):
        self.mainWin.pBtnApplyAnnotationDislay.clicked.connect(self.confirm) #应用标注展示
        self.mainWin.sliderTransparency.valueChanged.connect(self.setAlpha)
        self.mainWin.sliderSelectedTransparency.valueChanged.connect(self.setAlphaSelect)
        self.mainWin.comboBoxInstanceColor.currentTextChanged.connect(self.setInstanceColor) #设置标签颜色

    def stateInit(self):
        self.alpha = 127  # 默认透明度值
        self.alphaSelect = 191  # 默认选中透明度值
        self.instanceColor = "与类型一致"  # 默认实例颜色设置

    def show(self) -> None:
        self.project = self.parent.project
        if hasattr(self.project, 'labelAlpha'):
            self.alpha = self.project.labelAlpha
            self.alphaSelect = self.project.labelAlphaSelect
            self.mainWin.sliderTransparency.setValue(self.transparency(self.alpha))
            self.mainWin.sliderSelectedTransparency.setValue(self.transparency(self.alphaSelect))
            self.alphaBkup = self.alpha
            self.alphaSelectBkup = self.alphaSelect

        if hasattr(self.project, 'instanceColor'):#标签颜色设置相关
            index = self.mainWin.comboBoxInstanceColor.findText(self.project.instanceColor)
            if index >= 0:
                self.mainWin.comboBoxInstanceColor.setCurrentIndex(index)

        self.toSave = False
        self.reset()
        super().show()

    def hide(self) -> None:
        if not self.toSave:
            self.cancel()
        return super().hide()

    def transparency(self, alpha):
        return int((255 - alpha) / 255 * 100)

    def _trans_to_alpha(self, trans):
        return int((100 - trans) / 100 * 255)

    def confirm(self):
        self.toSave = True
        alpha = self._trans_to_alpha(self.mainWin.sliderTransparency.value())
        alphaSelect = self._trans_to_alpha(self.mainWin.sliderSelectedTransparency.value())

        if alpha > alphaSelect:
            dlg = Dialog('选中透明度始终不高于普通透明度')
            dlg.exec()
            self.AlphaSelectChanged.emit(alpha)
            self.mainWin.sliderSelectedTransparency.setValue(self.transparency(alpha))
        else:
            self.hide()
            self.project.labelAlpha = alpha
            self.project.labelAlphaSelect = alphaSelect
            self.project.instanceColor = self.mainWin.comboBoxInstanceColor.currentText()
            self.project.save()

    def reset(self):
        defaultAlpha = 127
        defaultAlphaSelect = 191
        defaultInstanceColor = "与类型一致"

        self.AlphaChanged.emit(defaultAlpha)
        self.AlphaSelectChanged.emit(defaultAlphaSelect)
        self.InstanceColorChanged.emit(defaultInstanceColor)

        self.mainWin.sliderTransparency.setValue(self.transparency(defaultAlpha))
        self.mainWin.sliderSelectedTransparency.setValue(self.transparency(defaultAlphaSelect))
        self.mainWin.comboBoxInstanceColor.setCurrentText(defaultInstanceColor)

    def cancel(self):
        self.AlphaChanged.emit(self.alphaBkup)
        self.AlphaSelectChanged.emit(self.alphaSelectBkup)
        self.InstanceColorChanged.emit(self.project.instanceColor)

        self.mainWin.sliderTransparency.setValue(self.transparency(self.alphaBkup))
        self.mainWin.sliderSelectedTransparency.setValue(self.transparency(self.alphaSelectBkup))
        self.mainWin.comboBoxInstanceColor.setCurrentText(self.project.instanceColor)

    def setAlpha(self):
        alpha = self._trans_to_alpha(self.mainWin.sliderTransparency.value())
        self.AlphaChanged.emit(alpha)
        self.mainWin.labelTransparencyTip.setText(f"透明度: {self.mainWin.sliderTransparency.value()}%")

    def setAlphaSelect(self):
        alphaSelect = self._trans_to_alpha(
            self.mainWin.sliderSelectedTransparency.value())
        self.AlphaSelectChanged.emit(alphaSelect)
        self.mainWin.labelSelectedTransparencyTip.setText(
            f"选中透明度: {self.mainWin.sliderSelectedTransparency.value()}%")

    def setInstanceColor(self, color):
        self.InstanceColorChanged.emit(color)

    def trans(self):
        if len(self.parent.project.classes) == 0:
            self.ui.toolButtonFold.setChecked(False)
            dlg = Dialog('请先在编辑-设定目标类型中设置标签')
            dlg.exec()
            self.parent.ui.tBtnArrow.click()
            return
        elif len(self.parent.fileList) == 0:
            self.ui.toolButtonFold.setChecked(False)
            dlg = Dialog('请先添加图片')
            dlg.exec()
            self.parent.ui.tBtnArrow.click()
            return
        if self.ui.toolButtonFold.isChecked():
            self.ui.widgetMain.setVisible(True)
            self.ui.toolButtonFold.setToolTip(QtCore.QCoreApplication.translate("Main", "折叠"))
            if self.win:
                self.ui.scrollArea.setWidget(self.win)
                self.show()
        else:
            self.reset()
            self.ui.widgetMain.setVisible(False)
            self.ui.toolButtonFold.setToolTip(QtCore.QCoreApplication.translate("Main", "展开"))


if __name__ == '__main__':
    QtCore.QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QtGui.QGuiApplication.setAttribute(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    myWin = LabelShow(None)
    myWin.show()
    sys.exit(app.exec_())