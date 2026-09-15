"""Hoja de estilos QSS global del POS La Loma (tema oscuro premium)."""

QSS_MAIN = """
* {
    font-family: 'Segoe UI', 'Noto Sans', sans-serif;
    font-size: 13px;
    font-weight: bold;
    outline: none;
}

QMainWindow, QDialog {
    background-color: #14161c;
}

QWidget#centralContainer {
    background-color: #14161c;
}

QLabel {
    color: #d3dae5;
}

QWidget#headerBar {
    background-color: #1b1f28;
    border-bottom: 2px solid #2fbf71;
}

QLabel#appTitle {
    color: #ffffff;
    font-size: 20px;
    font-weight: bold;
    padding-left: 14px;
}

QPushButton#navButton {
    background-color: transparent;
    color: #9aa4b2;
    border: none;
    border-radius: 6px;
    padding: 8px 10px;
    font-size: 13px;
    font-weight: bold;
}

QPushButton#navButton:hover {
    background-color: #232a36;
    color: #e6e9ef;
}

QPushButton#navButton:checked {
    background-color: #2fbf71;
    color: #0e1a12;
    font-weight: bold;
    font-size: 14px;
}

QPushButton {
    background-color: #262b36;
    color: #e6e9ef;
    border: 1px solid #343b49;
    border-radius: 6px;
    padding: 8px 14px;
    font-weight: bold;
}

QPushButton:hover {
    background-color: #2e3542;
    border-color: #454f63;
}

QPushButton:pressed {
    background-color: #1f242e;
}

QPushButton:disabled {
    background-color: #1a1e26;
    color: #5b6472;
    border-color: #262b36;
}

QPushButton#primaryButton {
    background-color: #2fbf71;
    color: #0e1a12;
    border: none;
    font-size: 16px;
    font-weight: bold;
    padding: 8px 14px;
}

QPushButton#primaryButton:hover {
    background-color: #3dd081;
}

QPushButton#primaryButton:pressed {
    background-color: #279d5c;
}

QPushButton#primaryButton[pulse="true"] {
    background-color: #4ade80;
}

QPushButton#dangerButton {
    background-color: #ef4444;
    color: #ffffff;
    border: none;
}

QPushButton#dangerButton:hover {
    background-color: #f87171;
}

QPushButton#dangerButton:pressed {
    background-color: #dc2626;
}

QPushButton#secondaryButton {
    background-color: #1f2530;
    color: #e6e9ef;
    border: 1px solid #2e3440;
    border-radius: 6px;
    padding: 8px 14px;
}

QPushButton#secondaryButton:hover {
    background-color: #262d3a;
    border-color: #3d4557;
}

QPushButton#secondaryButton:pressed {
    background-color: #1a1f28;
}

QPushButton#secondaryButton:disabled {
    background-color: #1a1e26;
    color: #5b6472;
    border-color: #262b36;
}

QPushButton#creditAction {
    background-color: rgba(245, 158, 11, 0.12);
    color: #f59e0b;
    border: 1px solid #f59e0b;
    border-radius: 6px;
    padding: 8px 12px;
    font-weight: bold;
}

QPushButton#creditAction:hover {
    background-color: rgba(245, 158, 11, 0.22);
}

QPushButton#creditAction:pressed {
    background-color: rgba(245, 158, 11, 0.30);
}

QPushButton#creditAction:disabled {
    background-color: #1a1e26;
    color: #5b6472;
    border-color: #262b36;
}

QPushButton#cancelOutline {
    background-color: transparent;
    color: #ef4444;
    border: 1px solid #7f1d1d;
    border-radius: 6px;
    padding: 8px 14px;
    font-weight: bold;
}

QPushButton#cancelOutline:hover {
    background-color: rgba(239, 68, 68, 0.12);
    border-color: #ef4444;
}

QPushButton#cancelOutline:pressed {
    background-color: rgba(239, 68, 68, 0.20);
}

QLabel#emptyState {
    color: #8b93a3;
    font-size: 14px;
    font-style: italic;
    padding: 16px;
}

QPushButton#paymentButton {
    background-color: #1f2530;
    color: #b9c2cf;
    border: 1px solid #2e3440;
    border-radius: 6px;
    padding: 8px 10px;
}

QPushButton#paymentButton:hover {
    background-color: #262d3a;
    border-color: #3d4557;
}

QPushButton#paymentButton:checked {
    background-color: #3b82f6;
    border-color: #3b82f6;
    color: #ffffff;
    font-weight: bold;
    font-size: 14px;
}

QPushButton#invoiceToggle {
    background-color: #1f2530;
    color: #b9c2cf;
    border: 1px solid #2e3440;
    border-radius: 6px;
    padding: 8px 10px;
}

QPushButton#invoiceToggle:hover {
    background-color: #262d3a;
    border-color: #3d4557;
}

QPushButton#invoiceToggle:checked {
    background-color: #f59e0b;
    border-color: #f59e0b;
    color: #1c1205;
    font-weight: bold;
    font-size: 14px;
}

QWidget#productCard {
    background-color: #1e222b;
    border: 1px solid #2a2f3a;
    border-radius: 8px;
}

QWidget#productCard:hover {
    background-color: #242a36;
    border-color: #2fbf71;
}

QWidget#productCard:pressed {
    background-color: #191d25;
}

QLabel#productCardImage {
    background-color: #232a36;
    border: 1px solid #2a2f3a;
    border-radius: 6px;
}

QLabel#productCardName {
    color: #e6e9ef;
    font-size: 14px;
    font-weight: bold;
}

QLabel#productCardPrice {
    color: #2fbf71;
    font-size: 17px;
    font-weight: bold;
}

QLabel#imagePreview {
    background-color: #232a36;
    border: 1px solid #2e3440;
    border-radius: 8px;
}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QTextEdit {
    background-color: #1a1e26;
    color: #e6e9ef;
    border: 1px solid #2e3440;
    border-radius: 6px;
    padding: 6px 10px;
    selection-background-color: #2fbf71;
    selection-color: #0e1a12;
}

QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QDateEdit:hover, QTextEdit:hover {
    border-color: #3d4557;
}

QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus, QTextEdit:focus {
    border-color: #2fbf71;
    background-color: #1d222c;
}

QDateEdit::drop-down {
    border: none;
    width: 26px;
}

QCalendarWidget QWidget {
    background-color: #1e222b;
    color: #e6e9ef;
}

QCalendarWidget QAbstractItemView:enabled {
    background-color: #1a1e26;
    color: #e6e9ef;
    selection-background-color: #2fbf71;
    selection-color: #0e1a12;
}

QCalendarWidget QToolButton {
    background-color: #1e222b;
    color: #e6e9ef;
    border: none;
    padding: 6px;
}

QLineEdit#searchInput {
    padding: 9px 12px;
    font-size: 14px;
}

QComboBox::drop-down {
    border: none;
    width: 26px;
}

QComboBox::down-arrow {
    width: 0px;
    height: 0px;
}

QComboBox QAbstractItemView {
    background-color: #1e222b;
    color: #e6e9ef;
    border: 1px solid #343b49;
    selection-background-color: #2fbf71;
    selection-color: #0e1a12;
    outline: none;
}

QSpinBox::up-button, QDoubleSpinBox::up-button {
    background-color: #262b36;
    border: none;
    border-radius: 3px;
    width: 18px;
}

QSpinBox::down-button, QDoubleSpinBox::down-button {
    background-color: #262b36;
    border: none;
    border-radius: 3px;
    width: 18px;
}

QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
    background-color: #343b49;
}

QTableWidget, QTableView {
    background-color: #161a21;
    color: #e6e9ef;
    border: 1px solid #2a2f3a;
    border-radius: 6px;
    gridline-color: #232836;
    selection-background-color: #2fbf71;
    selection-color: #0e1a12;
    alternate-background-color: #1a1f28;
}

QTableWidget::item, QTableView::item {
    padding: 4px 6px;
}

QHeaderView {
    background-color: #1e232d;
}

QHeaderView::section {
    background-color: #1e232d;
    color: #b9c2cf;
    border: none;
    border-bottom: 1px solid #2e3440;
    border-right: 1px solid #262c38;
    padding: 9px 12px;
    font-weight: bold;
    font-size: 14px;
}

QHeaderView#tableHeader::section {
    background-color: #1e232d;
    color: #b9c2cf;
    border: none;
    border-bottom: 1px solid #2e3440;
    border-right: 1px solid #262c38;
    padding: 9px 12px;
    font-weight: bold;
    font-size: 14px;
}

QTableCornerButton::section {
    background-color: #1e232d;
    border: none;
}

QTableWidget#cartTable {
    background-color: #12151b;
    color: #e6e9ef;
    border: 1px solid #2a2f3a;
    gridline-color: #1f242e;
    alternate-background-color: #171b23;
    selection-background-color: #2fbf71;
    selection-color: #0e1a12;
}

QTableWidget#cartTable::item {
    padding: 4px 6px;
}

QHeaderView#cartHeader::section {
    background-color: #1b1f28;
    color: #e6e9ef;
    border-bottom: 2px solid #2fbf71;
}

QWidget#cartPanel {
    background-color: #101318;
    border-left: 3px solid #2fbf71;
}

QLabel#cartPanelTitle {
    color: #ffffff;
    font-size: 16px;
    font-weight: bold;
}

QLabel#cartLabel {
    color: #8b93a3;
    font-size: 13px;
}

QLabel#cartValue {
    color: #ffffff;
    font-size: 13px;
}

QLabel#cartSectionTitle {
    color: #8b93a3;
    font-size: 12px;
    font-weight: bold;
}

QLabel#totalLabel {
    color: #0e1a12;
    font-size: 18px;
    font-weight: bold;
    background-color: #2fbf71;
    border-radius: 6px;
    padding: 10px 14px;
}

QLabel#totalLabel[pulse="true"] {
    background-color: #4ade80;
}

QLabel#sectionTitle {
    color: #eef2f8;
    font-size: 19px;
    font-weight: bold;
}

QLabel#subtitleLabel {
    color: #9aa4b2;
    font-size: 13px;
}

QLabel#statusValue {
    color: #eef2f8;
    font-size: 14px;
    font-weight: bold;
}

QScrollArea {
    border: none;
    background-color: transparent;
}

QScrollArea > QWidget > QWidget {
    background-color: #14161c;
}

QScrollBar:vertical {
    background: #14161c;
    width: 12px;
    border-radius: 6px;
}

QScrollBar::handle:vertical {
    background: #343b49;
    border-radius: 6px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background: #2fbf71;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    background: #14161c;
    height: 12px;
    border-radius: 6px;
}

QScrollBar::handle:horizontal {
    background: #343b49;
    border-radius: 6px;
    min-width: 30px;
}

QScrollBar::handle:horizontal:hover {
    background: #2fbf71;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

QStatusBar {
    background-color: #161a21;
    color: #b9c2cf;
    border-top: 1px solid #232836;
}

QStatusBar::item {
    border: none;
}

QStatusBar QLabel {
    color: #b9c2cf;
    font-size: 13px;
}

QListWidget {
    background-color: #1a1e26;
    color: #e6e9ef;
    border: 1px solid #2e3440;
    border-radius: 6px;
    outline: none;
}

QListWidget::item {
    padding: 6px 8px;
    border-bottom: 1px solid #232836;
}

QListWidget::item:hover {
    background-color: #242a36;
}

QListWidget::item:selected {
    background-color: #2fbf71;
    color: #0e1a12;
}

QGroupBox {
    background-color: #1e222b;
    border: 1px solid #2a2f3a;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 8px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #c9d1dd;
    font-weight: bold;
    font-size: 14px;
}

QToolTip {
    background-color: #1e222b;
    color: #e6e9ef;
    border: 1px solid #2fbf71;
    padding: 4px 8px;
    border-radius: 4px;
}

QMessageBox, QInputDialog {
    background-color: #1e222b;
}

QMessageBox QLabel, QInputDialog QLabel {
    color: #e6e9ef;
}

QMessageBox QPushButton, QInputDialog QPushButton {
    min-width: 80px;
}

QCheckBox {
    color: #d3dae5;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #3d4557;
    border-radius: 4px;
    background-color: #1a1e26;
}

QCheckBox::indicator:checked {
    background-color: #2fbf71;
    border-color: #2fbf71;
}

QRadioButton {
    color: #d3dae5;
}

QRadioButton::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #3d4557;
    border-radius: 8px;
    background-color: #1a1e26;
}

QRadioButton::indicator:checked {
    background-color: #2fbf71;
    border-color: #2fbf71;
}

QDialog#loginDialog {
    background-color: #14161c;
}

QLabel#loginTitle {
    color: #ffffff;
    font-size: 28px;
    font-weight: bold;
}

QLabel#loginSubtitle {
    color: #b9c2cf;
    font-size: 16px;
}

QLabel#loginError {
    color: #ef4444;
    font-size: 15px;
    min-height: 36px;
}

QLabel#loginError[hint="true"] {
    color: #b9c2cf;
}

QLineEdit#loginName {
    font-size: 16px;
    padding: 10px 12px;
}

QLineEdit#pinDisplay {
    font-size: 22px;
    letter-spacing: 8px;
    color: #ffffff;
    background-color: #1a1e26;
    border: 1px solid #2e3440;
    border-radius: 8px;
    padding: 10px;
    min-height: 44px;
}

QLineEdit#pinDisplay:focus {
    border-color: #2fbf71;
}

QPushButton#pinKey {
    background-color: #262b36;
    color: #e6e9ef;
    border: 1px solid #343b49;
    border-radius: 8px;
    font-size: 19px;
    font-weight: bold;
}

QPushButton#pinKey:hover {
    background-color: #2e3542;
    border-color: #2fbf71;
}

QPushButton#pinKey:pressed {
    background-color: #1f242e;
}

QPushButton#pinOk {
    background-color: #2fbf71;
    color: #0e1a12;
    border: none;
    border-radius: 8px;
    font-size: 22px;
    font-weight: bold;
}

QPushButton#pinOk:hover {
    background-color: #3dd081;
}

QPushButton#pinOk:pressed {
    background-color: #279d5c;
}

QPushButton#logoutButton {
    background-color: transparent;
    color: #9aa4b2;
    border: 1px solid #343b49;
    border-radius: 6px;
    padding: 6px 14px;
    margin-right: 10px;
}

QPushButton#logoutButton:hover {
    background-color: #232a36;
    color: #e6e9ef;
    border-color: #ef4444;
}

QWidget#reportToolbar {
    background-color: #1b1f28;
    border: 1px solid #2a2f3a;
    border-radius: 8px;
}

QPushButton#periodToggle {
    background-color: #1f2530;
    color: #b9c2cf;
    border: 1px solid #2e3440;
    border-radius: 6px;
    padding: 7px 16px;
}

QPushButton#periodToggle:hover {
    background-color: #262d3a;
    border-color: #3d4557;
}

QPushButton#periodToggle:checked {
    background-color: #2fbf71;
    border-color: #2fbf71;
    color: #0e1a12;
    font-weight: bold;
    font-size: 14px;
}

QFrame#statCard {
    background-color: #1b2030;
    border: 1px solid #2e3440;
    border-radius: 8px;
}

QFrame#separator {
    background-color: #2e3440;
    max-height: 1px;
}

QLabel#statTitle {
    color: #8b93a3;
    font-size: 13px;
}

QLabel#statValue {
    color: #ffffff;
    font-size: 22px;
    font-weight: bold;
}

QLabel#statValue[accent="true"] {
    color: #2fbf71;
}

QLabel#statValue[danger="true"] {
    color: #ef4444;
}

QPushButton#expenseButton {
    background-color: #f59e0b;
    color: #1c1205;
    border: none;
    border-radius: 6px;
    padding: 7px 16px;
    font-weight: bold;
    font-size: 14px;
}

QPushButton#expenseButton:hover {
    background-color: #fbbf24;
}

QLabel#settingsSubtitle {
    color: #8b93a3;
    font-size: 13px;
}

QGroupBox#settingsGroup {
    background-color: #1e222b;
    border: 1px solid #2a2f3a;
    border-radius: 10px;
    border-top: 2px solid #2fbf71;
    margin-top: 16px;
    padding: 16px 4px 10px 4px;
}

QGroupBox#settingsGroup::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 18px;
    padding: 0 8px;
    background-color: #1e222b;
    color: #eef2f8;
    font-size: 17px;
    font-weight: bold;
}

QLabel#formLabel {
    color: #9aa4b2;
    font-size: 13px;
}

QLabel#settingsHint {
    color: #5b6472;
    font-size: 13px;
}

QPushButton#toggleEye {
    background-color: #1a1e26;
    color: #9aa4b2;
    border: 1px solid #2e3440;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 13px;
}

QPushButton#toggleEye:hover {
    color: #e6e9ef;
    border-color: #3d4557;
}

QPushButton#toggleEye:checked {
    color: #2fbf71;
    border-color: #2fbf71;
}

QPushButton#testButton {
    background-color: #3b82f6;
    color: #ffffff;
    border: none;
    font-weight: bold;
    font-size: 14px;
}

QPushButton#testButton:hover {
    background-color: #60a5fa;
}

QPushButton#testButton:pressed {
    background-color: #2563eb;
}

QPushButton#resetButton {
    background-color: transparent;
    color: #9aa4b2;
    border: 1px solid #2e3440;
}

QPushButton#resetButton:hover {
    color: #e6e9ef;
    border-color: #3d4557;
}

QTabWidget#settingsTabs::pane {
    border: 1px solid #2a2f3a;
    border-radius: 8px;
    background-color: #161a21;
    top: -1px;
}

QTabWidget#settingsTabs QTabBar::tab {
    background-color: #1e232d;
    color: #9aa4b2;
    border: 1px solid #2a2f3a;
    border-bottom: none;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    padding: 8px 16px;
    margin-right: 4px;
    font-weight: bold;
}

QTabWidget#settingsTabs QTabBar::tab:hover {
    background-color: #262d3a;
    color: #e6e9ef;
}

QTabWidget#settingsTabs QTabBar::tab:selected {
    background-color: #2fbf71;
    color: #0e1a12;
    border-color: #2fbf71;
}
"""
