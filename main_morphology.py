from PyQt5.QtWidgets import *
from PyQt5.Qt import Qt
from PyQt5 import QtCore, QtGui
from PyQt5.QtCore import pyqtSignal
import sys
from wisdom_store.ui.main.Ui_Morphology import Ui_Morphology
import wisdom_store.ui.main.resources_rc
from wisdom_store.wins.main_foldingbar_item import FoldingBarItem
from wisdom_store.wins.main_dialog import Dialog


class Morphology(FoldingBarItem):
    # 定义单独的信号
    TargetTypeChanged = pyqtSignal(str)
    OperationTypeChanged = pyqtSignal(str)
    ParameterChanged = pyqtSignal(int)
    MorphologyReset = pyqtSignal()

    def __init__(self, parent):
        super(Morphology, self).__init__()
        self.parent = parent

        # 初始化窗口
        self.win = QWidget()
        self.mainWin = Ui_Morphology()
        self.mainWin.setupUi(self.win)
        self.set_content(self.win)
        self.set_title("形态学变换")

        # 隐藏系统默认框架
        self.setWindowFlags(Qt.FramelessWindowHint)

        # 设置鼠标追踪
        self.setMouseTracking(True)

        # 初始化操作类型下拉框
        self.mainWin.comboBoxOperationType.clear()
        operations = ["无", "膨胀", "腐蚀", "开运算", "闭运算", "小区域删除", "骨架化", "去枝权"]
        for op in operations:
            self.mainWin.comboBoxOperationType.addItem(op)

        # 事件绑定
        self.signalConnect()

        # 控件状态初始化
        self.stateInit()

    def signalConnect(self):
        self.mainWin.pBtnApplyMorphological.clicked.connect(self.confirm)
        self.mainWin.comboBoxTargetType.currentTextChanged.connect(self.onTargetTypeChanged)
        self.mainWin.comboBoxOperationType.currentTextChanged.connect(self.onOperationTypeChanged)
        self.mainWin.sliderParameterName.valueChanged.connect(self.onParameterChanged)

    def stateInit(self):
        self.targetType = ""
        self.operationType = "无"
        self.parameterValue = 1
        self.toSave = False
        self.hasManualAnnotation = False
        self.hasPrediction = False

    def show(self) -> None:
        self.project = self.parent.project
        # 初始化目标类型下拉框
        self.mainWin.comboBoxTargetType.clear()
        for cls in self.project.classes:
            self.mainWin.comboBoxTargetType.addItem(cls)

        # 检查当前图像状态
        self.checkImageStatus()

        self.reset()
        super().show()

    def hide(self) -> None:
        if not self.toSave:
            self.cancel()
        return super().hide()

    def checkImageStatus(self):
        # 检查当前图像是否有手动标注和预测结果
        currentFile = self.parent.getCurrentFile()
        self.hasManualAnnotation = currentFile.hasManualAnnotation() #检测是否有人工标注的mask
        self.hasPrediction = currentFile.hasPrediction() #检测是否有预测的mask

        if self.hasPrediction:
            dlg = Dialog('当前图像中含有已预测标注，请点击图像上方"确认"按钮，核验后再进行后处理')
            dlg.exec()

    def update_parameter_name(self):
        '''根据操作类型更新参数名和滑块范围'''
        current_operation = self.mainWin.comboBoxOperationType.currentText()

        if current_operation == "膨胀" or current_operation == "腐蚀" or \
                current_operation == "开运算" or current_operation == "闭运算" \
                or current_operation == "去枝权":
            self.mainWin.labelParameterName.setText("迭代次数：")
            self.mainWin.sliderParameterName.setMinimum(1)
            self.mainWin.sliderParameterName.setMaximum(10)
            self.mainWin.sliderParameterName.setValue(1)
            self.mainWin.labelParameterNameMin.setText("1")
            self.mainWin.labelParameterNameMax.setText("10")
        elif current_operation == "小区域删除":
            self.mainWin.labelParameterName.setText("区域大小：")
            self.mainWin.sliderParameterName.setMinimum(1)
            self.mainWin.sliderParameterName.setMaximum(1000)
            self.mainWin.sliderParameterName.setValue(1)
            self.mainWin.labelParameterNameMin.setText("1")
            self.mainWin.labelParameterNameMax.setText("1000")
        elif current_operation == "骨架化":
            self.mainWin.labelParameterName.setText("骨架宽度：")
            self.mainWin.sliderParameterName.setMinimum(1)
            self.mainWin.sliderParameterName.setMaximum(10)
            self.mainWin.sliderParameterName.setValue(1)
            self.mainWin.labelParameterNameMin.setText("1")
            self.mainWin.labelParameterNameMax.setText("10")
        else:  # "无"操作
            self.mainWin.labelParameterName.setText("参数名：")
            self.mainWin.sliderParameterName.setMinimum(1)
            self.mainWin.sliderParameterName.setMaximum(10)
            self.mainWin.sliderParameterName.setValue(1)
            self.mainWin.labelParameterNameMin.setText("1")
            self.mainWin.labelParameterNameMax.setText("10")

        # 更新当前参数值显示
        self.updateParamValue()

    def updateParamValue(self):
        self.parameterValue = self.mainWin.sliderParameterName.value()
        self.mainWin.labelParameterName.setText(f"参数值: {self.parameterValue}")
        self.ParameterChanged.emit(self.parameterValue)

    def onTargetTypeChanged(self, targetType):
        self.targetType = targetType
        self.TargetTypeChanged.emit(targetType)

    def onOperationTypeChanged(self, operationType):
        self.operationType = operationType
        self.update_parameter_name()
        self.OperationTypeChanged.emit(operationType)

    def onParameterChanged(self, value):
        self.parameterValue = value
        self.updateParamValue()

    def confirm(self):
        if not self.hasManualAnnotation:
            dlg = Dialog('当前图像没有人工标注的画刷标注，请标注后再进行后处理 ')
            dlg.exec()
            return

        self.toSave = True
        if self.operationType == "无":
            self.MorphologyReset.emit()
        else:
            pass

        self.reset()
        self.hide()

    def reset(self):
        self.mainWin.comboBoxOperationType.setCurrentIndex(0)
        self.update_parameter_name()
        self.MorphologyReset.emit()

    def cancel(self):
        self.MorphologyReset.emit()
        self.reset()

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
            self.cancel()
            self.ui.widgetMain.setVisible(False)
            self.ui.toolButtonFold.setToolTip(QtCore.QCoreApplication.translate("Main", "展开"))


if __name__ == '__main__':
    QtCore.QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QtGui.QGuiApplication.setAttribute(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    myWin = Morphology(None)
    myWin.show()
    sys.exit(app.exec_())