from PyQt6.QtWidgets import QLabel, QMenu
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtGui import QCursor
from core.qlibhelper import MARKETS

from core.app_state import get_state


class RegionLabel(QLabel):
    def __init__(self, parent=None, needChangeText = True):
        super().__init__(parent)
        self.state = get_state()
        self.needChangeText = needChangeText

        if self.needChangeText == True :
            self.setText(f"REG: {self.state.reg_name}")
            self.setStyleSheet("color: #888; font-size: 12px;")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.show_menu(event.globalPosition().toPoint())

    def get_regName(self, reg) -> str:
        regName = ""
        for regkey, reg_name in MARKETS:
            if regkey == reg:
                regName = reg_name
        return regName
    def show_menu(self, pos):
        menu = QMenu(self)

        for reg, reg_name in MARKETS:
            action = menu.addAction(f"{reg_name} ({reg.upper()})")
            action.setData(reg)

            # 高亮当前选中
            if reg == self.state.reg:
                action.setCheckable(True)
                action.setChecked(True)

        selected_action = menu.exec(pos)
        if selected_action:
            reg = selected_action.data()
            reg_name = self.get_regName(reg)

            if self.needChangeText == True :
                self.setText(f"REG: {reg_name}")
            self.state.reg = reg
            self.state.reg_name = reg_name
            
            # app.setApplicationDisplayName(f"QuantByQlib — {reg_name}量化辅助决策平台")
            # self.setWindowTitle(f"QuantByQlib — {reg_name}量化辅助决策平台")
            # 触发全局事件通知其他组件（如主窗口）更新显示
            
            from core.event_bus import get_event_bus
            bus = get_event_bus()
            bus.reg_changed.emit(reg, reg_name)
            