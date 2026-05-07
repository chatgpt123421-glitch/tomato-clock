#!/usr/bin/env python3
"""桌面番茄钟应用 - PySide6"""

import sys
import time
from enum import Enum, auto

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSpinBox, QSystemTrayIcon, QMenu, QStyle
)
from PySide6.QtCore import Qt, QTimer, Signal, QSize
from PySide6.QtGui import QFont, QAction, QIcon, QCloseEvent


class TimerState(Enum):
    IDLE = auto()
    WORKING = auto()
    SHORT_BREAK = auto()
    LONG_BREAK = auto()
    PAUSED = auto()


class PomodoroTimer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("番茄钟")
        self.setMinimumSize(400, 500)
        self.setMaximumSize(400, 500)

        # 配置（分钟）
        self.work_duration = 25
        self.short_break = 5
        self.long_break = 15

        # 状态
        self.state = TimerState.IDLE
        self.remaining_seconds = self.work_duration * 60
        self.completed_sessions = 0

        self._setup_ui()
        self._setup_timer()
        self._setup_tray()
        self.update_display()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)

        # 标题
        self.title_label = QLabel("专注时间")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setFont(QFont("Microsoft YaHei", 18, QFont.Weight.Bold))
        layout.addWidget(self.title_label)

        # 倒计时显示
        self.time_label = QLabel("25:00")
        self.time_label.setAlignment(Qt.AlignCenter)
        self.time_label.setFont(QFont("Microsoft YaHei", 64, QFont.Weight.Bold))
        self.time_label.setStyleSheet("color: #FF6B6B;")
        layout.addWidget(self.time_label)

        # 状态标签
        self.status_label = QLabel("准备开始")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setFont(QFont("Microsoft YaHei", 12))
        layout.addWidget(self.status_label)

        # 进度指示
        self.session_label = QLabel(f"今日完成: {self.completed_sessions} 个番茄")
        self.session_label.setAlignment(Qt.AlignCenter)
        self.session_label.setFont(QFont("Microsoft YaHei", 10))
        layout.addWidget(self.session_label)

        layout.addSpacing(10)

        # 控制按钮
        btn_layout = QHBoxLayout()

        self.start_btn = QPushButton("开始")
        self.start_btn.setFont(QFont("Microsoft YaHei", 12))
        self.start_btn.setMinimumHeight(45)
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #4ECDC4;
                color: white;
                border: none;
                border-radius: 8px;
            }
            QPushButton:hover { background-color: #45B7AA; }
        """)
        self.start_btn.clicked.connect(self.on_start)

        self.pause_btn = QPushButton("暂停")
        self.pause_btn.setFont(QFont("Microsoft YaHei", 12))
        self.pause_btn.setMinimumHeight(45)
        self.pause_btn.setStyleSheet("""
            QPushButton {
                background-color: #FFB347;
                color: white;
                border: none;
                border-radius: 8px;
            }
            QPushButton:hover { background-color: #E6A13E; }
        """)
        self.pause_btn.clicked.connect(self.on_pause)
        self.pause_btn.setVisible(False)

        self.reset_btn = QPushButton("重置")
        self.reset_btn.setFont(QFont("Microsoft YaHei", 12))
        self.reset_btn.setMinimumHeight(45)
        self.reset_btn.setStyleSheet("""
            QPushButton {
                background-color: #95A5A6;
                color: white;
                border: none;
                border-radius: 8px;
            }
            QPushButton:hover { background-color: #7F8C8D; }
        """)
        self.reset_btn.clicked.connect(self.on_reset)

        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.pause_btn)
        btn_layout.addWidget(self.reset_btn)
        layout.addLayout(btn_layout)

        layout.addSpacing(10)

        # 模式按钮
        mode_layout = QHBoxLayout()

        self.work_btn = QPushButton("专注")
        self.work_btn.setCheckable(True)
        self.work_btn.setChecked(True)
        self.work_btn.setStyleSheet(self._mode_btn_style("#FF6B6B"))
        self.work_btn.clicked.connect(lambda: self.switch_mode(TimerState.WORKING))

        self.short_btn = QPushButton("短休")
        self.short_btn.setCheckable(True)
        self.short_btn.setStyleSheet(self._mode_btn_style("#4ECDC4"))
        self.short_btn.clicked.connect(lambda: self.switch_mode(TimerState.SHORT_BREAK))

        self.long_btn = QPushButton("长休")
        self.long_btn.setCheckable(True)
        self.long_btn.setStyleSheet(self._mode_btn_style("#9B59B6"))
        self.long_btn.clicked.connect(lambda: self.switch_mode(TimerState.LONG_BREAK))

        mode_layout.addWidget(self.work_btn)
        mode_layout.addWidget(self.short_btn)
        mode_layout.addWidget(self.long_btn)
        layout.addLayout(mode_layout)

        # 设置区域
        settings_layout = QHBoxLayout()

        settings_layout.addWidget(QLabel("专注:"))
        self.work_spin = QSpinBox()
        self.work_spin.setRange(1, 60)
        self.work_spin.setValue(self.work_duration)
        self.work_spin.valueChanged.connect(self.update_work_duration)
        settings_layout.addWidget(self.work_spin)

        settings_layout.addWidget(QLabel("短休:"))
        self.short_spin = QSpinBox()
        self.short_spin.setRange(1, 30)
        self.short_spin.setValue(self.short_break)
        self.short_spin.valueChanged.connect(self.update_short_break)
        settings_layout.addWidget(self.short_spin)

        settings_layout.addWidget(QLabel("长休:"))
        self.long_spin = QSpinBox()
        self.long_spin.setRange(1, 60)
        self.long_spin.setValue(self.long_break)
        self.long_spin.valueChanged.connect(self.update_long_break)
        settings_layout.addWidget(self.long_spin)

        layout.addLayout(settings_layout)

    def _mode_btn_style(self, color):
        return f"""
            QPushButton {{
                padding: 8px;
                border: 2px solid {color};
                border-radius: 6px;
                background-color: white;
                color: {color};
                font-weight: bold;
            }}
            QPushButton:checked {{
                background-color: {color};
                color: white;
            }}
        """

    def _setup_timer(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.setInterval(1000)

    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setToolTip("番茄钟")

        # 创建托盘菜单
        tray_menu = QMenu()

        show_action = QAction("显示", self)
        show_action.triggered.connect(self.show_normal)

        start_action = QAction("开始/暂停", self)
        start_action.triggered.connect(self.toggle_timer)

        quit_action = QAction("退出", self)
        quit_action.triggered.connect(QApplication.quit)

        tray_menu.addAction(show_action)
        tray_menu.addAction(start_action)
        tray_menu.addSeparator()
        tray_menu.addAction(quit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.on_tray_activated)
        self.tray_icon.show()

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_normal()

    def show_normal(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def update_work_duration(self, val):
        self.work_duration = val
        if self.state in (TimerState.IDLE, TimerState.PAUSED) and self.work_btn.isChecked():
            self.remaining_seconds = val * 60
            self.update_display()

    def update_short_break(self, val):
        self.short_break = val

    def update_long_break(self, val):
        self.long_break = val

    def switch_mode(self, mode):
        self.work_btn.setChecked(mode == TimerState.WORKING)
        self.short_btn.setChecked(mode == TimerState.SHORT_BREAK)
        self.long_btn.setChecked(mode == TimerState.LONG_BREAK)

        self.on_reset()

    def get_current_duration(self):
        if self.work_btn.isChecked():
            return self.work_duration * 60
        elif self.short_btn.isChecked():
            return self.short_break * 60
        else:
            return self.long_break * 60

    def on_start(self):
        if self.state == TimerState.PAUSED:
            self.state = TimerState.WORKING if self.work_btn.isChecked() else \
                        TimerState.SHORT_BREAK if self.short_btn.isChecked() else TimerState.LONG_BREAK
        else:
            self.state = TimerState.WORKING if self.work_btn.isChecked() else \
                        TimerState.SHORT_BREAK if self.short_btn.isChecked() else TimerState.LONG_BREAK

        self.start_btn.setVisible(False)
        self.pause_btn.setVisible(True)
        self.status_label.setText("进行中..." if self.work_btn.isChecked() else "休息中...")
        self.timer.start()

    def on_pause(self):
        self.state = TimerState.PAUSED
        self.timer.stop()
        self.start_btn.setVisible(True)
        self.pause_btn.setVisible(False)
        self.status_label.setText("已暂停")
        self.start_btn.setText("继续")

    def on_reset(self):
        self.timer.stop()
        self.state = TimerState.IDLE
        self.remaining_seconds = self.get_current_duration()
        self.start_btn.setVisible(True)
        self.pause_btn.setVisible(False)
        self.start_btn.setText("开始")
        self.status_label.setText("准备开始")
        self.update_display()

    def toggle_timer(self):
        if self.state in (TimerState.IDLE, TimerState.PAUSED):
            self.on_start()
        else:
            self.on_pause()

    def tick(self):
        self.remaining_seconds -= 1
        self.update_display()

        if self.remaining_seconds <= 0:
            self.timer_finished()

    def timer_finished(self):
        self.timer.stop()

        if self.work_btn.isChecked():
            self.completed_sessions += 1
            self.session_label.setText(f"今日完成: {self.completed_sessions} 个番茄")
            self.status_label.setText("专注完成！休息一下吧")

            # 自动切换到短休
            if self.completed_sessions % 4 == 0:
                self.long_btn.setChecked(True)
                self.work_btn.setChecked(False)
            else:
                self.short_btn.setChecked(True)
                self.work_btn.setChecked(False)
        else:
            self.status_label.setText("休息结束！准备专注")
            self.work_btn.setChecked(True)
            self.short_btn.setChecked(False)
            self.long_btn.setChecked(False)

        self.state = TimerState.IDLE
        self.remaining_seconds = self.get_current_duration()
        self.start_btn.setVisible(True)
        self.pause_btn.setVisible(False)
        self.start_btn.setText("开始")
        self.update_display()

        # 系统通知
        if hasattr(self, 'tray_icon'):
            self.tray_icon.showMessage(
                "番茄钟",
                "时间到！" if self.work_btn.isChecked() else "休息结束，开始专注吧！",
                QSystemTrayIcon.Information,
                3000
            )

    def update_display(self):
        minutes = self.remaining_seconds // 60
        seconds = self.remaining_seconds % 60
        time_str = f"{minutes:02d}:{seconds:02d}"
        self.time_label.setText(time_str)

        # 更新托盘提示
        if hasattr(self, 'tray_icon'):
            self.tray_icon.setToolTip(f"番茄钟 - {time_str}")

    def closeEvent(self, event: QCloseEvent):
        # 最小化到托盘而不是退出
        if hasattr(self, 'tray_icon') and self.tray_icon.isVisible():
            self.hide()
            event.ignore()
        else:
            event.accept()


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # 设置应用样式
    app.setStyleSheet("""
        QMainWindow {
            background-color: #F8F9FA;
        }
        QWidget {
            font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
        }
        QSpinBox {
            padding: 5px;
            border: 1px solid #DDD;
            border-radius: 4px;
            min-width: 50px;
        }
    """)

    window = PomodoroTimer()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
