"""Plantilla QSS global del POS La Loma (colores como @tokens@).

Los tokens se resuelven en `ui/theme.py` según la apariencia elegida
(tema, color de acento, tamaño y densidad). No editar los colores a mano:
agregue o cambie tokens en `ui/theme.py`.
"""

QSS_TEMPLATE = """
* {
    font-family: 'Segoe UI', 'Noto Sans', sans-serif;
    font-size: 13px;
    font-weight: bold;
    outline: none;
}

QMainWindow, QDialog {
    background-color: @bg@;
}

QWidget#centralContainer {
    background-color: @bg@;
}

QLabel {
    color: @text_dim@;
}

QWidget#headerBar {
    background-color: @header@;
    border-bottom: 2px solid @accent@;
}

QLabel#appTitle {
    color: @text_bright@;
    font-size: 20px;
    font-weight: bold;
    padding-left: 14px;
}

QPushButton#navButton {
    background-color: transparent;
    color: @text_muted@;
    border: none;
    border-radius: 6px;
    padding: 8px 10px;
    font-size: 13px;
    font-weight: bold;
}

QPushButton#navButton:hover {
    background-color: @surface@;
    color: @text@;
}

QPushButton#navButton:checked {
    background-color: @accent@;
    color: @on_accent@;
    font-weight: bold;
    font-size: 14px;
}

QPushButton {
    background-color: @button@;
    color: @text@;
    border: 1px solid @border3@;
    border-radius: 6px;
    padding: 8px 14px;
    font-weight: bold;
}

QPushButton:hover {
    background-color: @nav_hover@;
    border-color: @border_hover2@;
}

QPushButton:pressed {
    background-color: @pressed@;
}

QPushButton:disabled {
    background-color: @input@;
    color: @text_disabled@;
    border-color: @button@;
}

QPushButton#primaryButton {
    background-color: @accent@;
    color: @on_accent@;
    border: none;
    font-size: 16px;
    font-weight: bold;
    padding: 8px 14px;
}

QPushButton#primaryButton:hover {
    background-color: @accent_hover@;
}

QPushButton#primaryButton:pressed {
    background-color: @accent_pressed@;
}

QPushButton#primaryButton[pulse="true"] {
    background-color: @accent_bright@;
}

QPushButton#dangerButton {
    background-color: @danger@;
    color: @text_bright@;
    border: none;
}

QPushButton#dangerButton:hover {
    background-color: @danger_hover@;
}

QPushButton#dangerButton:pressed {
    background-color: @danger_pressed@;
}

QPushButton#secondaryButton {
    background-color: @button_secondary@;
    color: @text@;
    border: 1px solid @border2@;
    border-radius: 6px;
    padding: 8px 14px;
}

QPushButton#secondaryButton:hover {
    background-color: @button_hover@;
    border-color: @border_hover@;
}

QPushButton#secondaryButton:pressed {
    background-color: @table_alt@;
}

QPushButton#secondaryButton:disabled {
    background-color: @input@;
    color: @text_disabled@;
    border-color: @button@;
}

QPushButton#creditAction {
    background-color: @warn_a12@;
    color: @warn@;
    border: 1px solid @warn@;
    border-radius: 6px;
    padding: 8px 12px;
    font-weight: bold;
}

QPushButton#creditAction:hover {
    background-color: @warn_a22@;
}

QPushButton#creditAction:pressed {
    background-color: @warn_a30@;
}

QPushButton#creditAction:disabled {
    background-color: @input@;
    color: @text_disabled@;
    border-color: @button@;
}

QPushButton#cancelOutline {
    background-color: transparent;
    color: @danger@;
    border: 1px solid @danger_border@;
    border-radius: 6px;
    padding: 8px 14px;
    font-weight: bold;
}

QPushButton#cancelOutline:hover {
    background-color: @danger_a12@;
    border-color: @danger@;
}

QPushButton#cancelOutline:pressed {
    background-color: @danger_a20@;
}

QLabel#emptyState {
    color: @text_faint@;
    font-size: 14px;
    font-style: italic;
    padding: 16px;
}

QLabel#chipCredit {
    background-color: @info_a28@;
    color: @info_soft_text@;
    border: 1px solid @info@;
    border-radius: 10px;
    padding: 3px 12px;
    font-size: 13px;
}

QLabel#chipOrder {
    background-color: @warn_a30@;
    color: @warn_soft_text@;
    border: 1px solid @warn@;
    border-radius: 10px;
    padding: 3px 12px;
    font-size: 13px;
}

/* Visor de vista previa del ticket (estilo Chrome) */
QWidget#previewFondo {
    background-color: @bg_deep@;
}

QLabel#previewHoja {
    background-color: @text_bright@;
    border: 1px solid @border@;
}

QWidget#previewPanel {
    background-color: @bg@;
    border-left: 1px solid @border@;
}

QLabel#previewTitulo {
    color: @text_bright@;
    font-size: 16px;
    font-weight: bold;
}

QLabel#previewEtiqueta {
    color: @text_faint@;
    font-size: 12px;
    font-weight: bold;
}

QLabel#previewZoom {
    color: @text_dim@;
}

QLabel#previewAviso {
    background-color: @warn_a14@;
    color: @warn_soft_text2@;
    border: 1px solid @warn_a45@;
    border-radius: 6px;
    padding: 8px;
    font-size: 12px;
}

QPushButton#paymentButton {
    background-color: @button_secondary@;
    color: @text_dim2@;
    border: 1px solid @border2@;
    border-radius: 6px;
    padding: 8px 10px;
}

QPushButton#paymentButton:hover {
    background-color: @button_hover@;
    border-color: @border_hover@;
}

QPushButton#paymentButton:checked {
    background-color: @info@;
    border-color: @info@;
    color: @text_bright@;
    font-weight: bold;
    font-size: 14px;
}

QPushButton#invoiceToggle {
    background-color: @button_secondary@;
    color: @text_dim2@;
    border: 1px solid @border2@;
    border-radius: 6px;
    padding: 8px 10px;
}

QPushButton#invoiceToggle:hover {
    background-color: @button_hover@;
    border-color: @border_hover@;
}

QPushButton#invoiceToggle:checked {
    background-color: @warn@;
    border-color: @warn@;
    color: @warn_on@;
    font-weight: bold;
    font-size: 14px;
}

QWidget#productCard {
    background-color: @panel@;
    border: 1px solid @border@;
    border-radius: 8px;
}

QWidget#productCard:hover {
    background-color: @hover@;
    border-color: @accent@;
}

QWidget#productCard:pressed {
    background-color: @card_pressed@;
}

QLabel#productCardImage {
    background-color: @surface@;
    border: 1px solid @border@;
    border-radius: 6px;
}

QLabel#productCardName {
    color: @text@;
    font-size: 14px;
    font-weight: bold;
}

QLabel#productCardPrice {
    color: @accent@;
    font-size: 17px;
    font-weight: bold;
}

QLabel#imagePreview {
    background-color: @surface@;
    border: 1px solid @border2@;
    border-radius: 8px;
}

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QTextEdit {
    background-color: @input@;
    color: @text@;
    border: 1px solid @border2@;
    border-radius: 6px;
    padding: 6px 10px;
    selection-background-color: @accent@;
    selection-color: @on_accent@;
}

QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QDateEdit:hover, QTextEdit:hover {
    border-color: @border_hover@;
}

QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus, QTextEdit:focus {
    border-color: @accent@;
    background-color: @input_focus@;
}

QDateEdit::drop-down {
    border: none;
    width: 26px;
}

QCalendarWidget QWidget {
    background-color: @panel@;
    color: @text@;
}

QCalendarWidget QAbstractItemView:enabled {
    background-color: @input@;
    color: @text@;
    selection-background-color: @accent@;
    selection-color: @on_accent@;
}

QCalendarWidget QToolButton {
    background-color: @panel@;
    color: @text@;
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
    background-color: @panel@;
    color: @text@;
    border: 1px solid @border3@;
    selection-background-color: @accent@;
    selection-color: @on_accent@;
    outline: none;
}

QSpinBox::up-button, QDoubleSpinBox::up-button {
    background-color: @button@;
    border: none;
    border-radius: 3px;
    width: 18px;
}

QSpinBox::down-button, QDoubleSpinBox::down-button {
    background-color: @button@;
    border: none;
    border-radius: 3px;
    width: 18px;
}

QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
    background-color: @border3@;
}

QTableWidget, QTableView {
    background-color: @bg_panel@;
    color: @text@;
    border: 1px solid @border@;
    border-radius: 6px;
    gridline-color: @gridline@;
    selection-background-color: @accent@;
    selection-color: @on_accent@;
    alternate-background-color: @table_alt@;
}

QTableWidget::item, QTableView::item {
    padding: 4px 6px;
}

QHeaderView {
    background-color: @header_section@;
}

QHeaderView::section {
    background-color: @header_section@;
    color: @text_dim2@;
    border: none;
    border-bottom: 1px solid @border2@;
    border-right: 1px solid @border_grid@;
    padding: 9px 12px;
    font-weight: bold;
    font-size: 14px;
}

QHeaderView#tableHeader::section {
    background-color: @header_section@;
    color: @text_dim2@;
    border: none;
    border-bottom: 1px solid @border2@;
    border-right: 1px solid @border_grid@;
    padding: 9px 12px;
    font-weight: bold;
    font-size: 14px;
}

QTableCornerButton::section {
    background-color: @header_section@;
    border: none;
}

QTableWidget#cartTable {
    background-color: @cart_table_bg@;
    color: @text@;
    border: 1px solid @border@;
    gridline-color: @pressed@;
    alternate-background-color: @cart_alt@;
    selection-background-color: @accent@;
    selection-color: @on_accent@;
}

QTableWidget#cartTable::item {
    padding: 4px 6px;
}

QHeaderView#cartHeader::section {
    background-color: @header@;
    color: @text@;
    border-bottom: 2px solid @accent@;
}

QWidget#cartPanel {
    background-color: @cart_panel_bg@;
    border-left: 3px solid @accent@;
}

QLabel#cartPanelTitle {
    color: @text_bright@;
    font-size: 16px;
    font-weight: bold;
}

QLabel#cartLabel {
    color: @text_faint@;
    font-size: 13px;
}

QLabel#cartValue {
    color: @text_bright@;
    font-size: 13px;
}

QLabel#cartSectionTitle {
    color: @text_faint@;
    font-size: 12px;
    font-weight: bold;
}

QLabel#totalLabel {
    color: @on_accent@;
    font-size: 18px;
    font-weight: bold;
    background-color: @accent@;
    border-radius: 6px;
    padding: 10px 14px;
}

QLabel#totalLabel[pulse="true"] {
    background-color: @accent_bright@;
}

QLabel#sectionTitle {
    color: @text_strong@;
    font-size: 19px;
    font-weight: bold;
}

QLabel#subtitleLabel {
    color: @text_muted@;
    font-size: 13px;
}

QLabel#statusValue {
    color: @text_strong@;
    font-size: 14px;
    font-weight: bold;
}

QScrollArea {
    border: none;
    background-color: transparent;
}

QScrollArea > QWidget > QWidget {
    background-color: @bg@;
}

QScrollBar:vertical {
    background: @bg@;
    width: 12px;
    border-radius: 6px;
}

QScrollBar::handle:vertical {
    background: @border3@;
    border-radius: 6px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background: @accent@;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    background: @bg@;
    height: 12px;
    border-radius: 6px;
}

QScrollBar::handle:horizontal {
    background: @border3@;
    border-radius: 6px;
    min-width: 30px;
}

QScrollBar::handle:horizontal:hover {
    background: @accent@;
}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

QStatusBar {
    background-color: @bg_panel@;
    color: @text_dim2@;
    border-top: 1px solid @gridline@;
}

QStatusBar::item {
    border: none;
}

QStatusBar QLabel {
    color: @text_dim2@;
    font-size: 13px;
}

QListWidget {
    background-color: @input@;
    color: @text@;
    border: 1px solid @border2@;
    border-radius: 6px;
    outline: none;
}

QListWidget::item {
    padding: 6px 8px;
    border-bottom: 1px solid @gridline@;
}

QListWidget::item:hover {
    background-color: @hover@;
}

QListWidget::item:selected {
    background-color: @accent@;
    color: @on_accent@;
}

QGroupBox {
    background-color: @panel@;
    border: 1px solid @border@;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 8px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: @text_title@;
    font-weight: bold;
    font-size: 14px;
}

QToolTip {
    background-color: @panel@;
    color: @text@;
    border: 1px solid @accent@;
    padding: 4px 8px;
    border-radius: 4px;
}

QMessageBox, QInputDialog {
    background-color: @panel@;
}

QMessageBox QLabel, QInputDialog QLabel {
    color: @text@;
}

QMessageBox QPushButton, QInputDialog QPushButton {
    min-width: 80px;
}

QCheckBox {
    color: @text_dim@;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid @border_hover@;
    border-radius: 4px;
    background-color: @input@;
}

QCheckBox::indicator:checked {
    background-color: @accent@;
    border-color: @accent@;
}

QRadioButton {
    color: @text_dim@;
}

QRadioButton::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid @border_hover@;
    border-radius: 8px;
    background-color: @input@;
}

QRadioButton::indicator:checked {
    background-color: @accent@;
    border-color: @accent@;
}

QDialog#loginDialog {
    background-color: @bg@;
}

QLabel#loginTitle {
    color: @text_bright@;
    font-size: 28px;
    font-weight: bold;
}

QLabel#loginSubtitle {
    color: @text_dim2@;
    font-size: 16px;
}

QLabel#loginError {
    color: @danger@;
    font-size: 15px;
    min-height: 36px;
}

QLabel#loginError[hint="true"] {
    color: @text_dim2@;
}

QLineEdit#loginName {
    font-size: 16px;
    padding: 10px 12px;
}

QLineEdit#pinDisplay {
    font-size: 22px;
    letter-spacing: 8px;
    color: @text_bright@;
    background-color: @input@;
    border: 1px solid @border2@;
    border-radius: 8px;
    padding: 10px;
    min-height: 44px;
}

QLineEdit#pinDisplay:focus {
    border-color: @accent@;
}

QPushButton#pinKey {
    background-color: @button@;
    color: @text@;
    border: 1px solid @border3@;
    border-radius: 8px;
    font-size: 19px;
    font-weight: bold;
}

QPushButton#pinKey:hover {
    background-color: @nav_hover@;
    border-color: @accent@;
}

QPushButton#pinKey:pressed {
    background-color: @pressed@;
}

QPushButton#pinOk {
    background-color: @accent@;
    color: @on_accent@;
    border: none;
    border-radius: 8px;
    font-size: 22px;
    font-weight: bold;
}

QPushButton#pinOk:hover {
    background-color: @accent_hover@;
}

QPushButton#pinOk:pressed {
    background-color: @accent_pressed@;
}

QPushButton#logoutButton {
    background-color: transparent;
    color: @text_muted@;
    border: 1px solid @border3@;
    border-radius: 6px;
    padding: 6px 14px;
    margin-right: 10px;
}

QPushButton#logoutButton:hover {
    background-color: @surface@;
    color: @text@;
    border-color: @danger@;
}

QWidget#reportToolbar {
    background-color: @header@;
    border: 1px solid @border@;
    border-radius: 8px;
}

QPushButton#periodToggle {
    background-color: @button_secondary@;
    color: @text_dim2@;
    border: 1px solid @border2@;
    border-radius: 6px;
    padding: 7px 16px;
}

QPushButton#periodToggle:hover {
    background-color: @button_hover@;
    border-color: @border_hover@;
}

QPushButton#periodToggle:checked {
    background-color: @accent@;
    border-color: @accent@;
    color: @on_accent@;
    font-weight: bold;
    font-size: 14px;
}

QFrame#statCard {
    background-color: @stat_card@;
    border: 1px solid @border2@;
    border-radius: 8px;
}

QFrame#separator {
    background-color: @border2@;
    max-height: 1px;
}

QLabel#statTitle {
    color: @text_faint@;
    font-size: 13px;
}

QLabel#statValue {
    color: @text_bright@;
    font-size: 22px;
    font-weight: bold;
}

QLabel#statValue[accent="true"] {
    color: @accent@;
}

QLabel#statValue[danger="true"] {
    color: @danger@;
}

QPushButton#expenseButton {
    background-color: @warn@;
    color: @warn_on@;
    border: none;
    border-radius: 6px;
    padding: 7px 16px;
    font-weight: bold;
    font-size: 14px;
}

QPushButton#expenseButton:hover {
    background-color: @warn_hover@;
}

QLabel#settingsSubtitle {
    color: @text_faint@;
    font-size: 13px;
}

QGroupBox#settingsGroup {
    background-color: @panel@;
    border: 1px solid @border@;
    border-radius: 10px;
    border-top: 2px solid @accent@;
    margin-top: 16px;
    padding: 16px 4px 10px 4px;
}

QGroupBox#settingsGroup::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 18px;
    padding: 0 8px;
    background-color: @panel@;
    color: @text_strong@;
    font-size: 17px;
    font-weight: bold;
}

QLabel#formLabel {
    color: @text_muted@;
    font-size: 13px;
}

QLabel#settingsHint {
    color: @text_disabled@;
    font-size: 13px;
}

QPushButton#toggleEye {
    background-color: @input@;
    color: @text_muted@;
    border: 1px solid @border2@;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 13px;
}

QPushButton#toggleEye:hover {
    color: @text@;
    border-color: @border_hover@;
}

QPushButton#toggleEye:checked {
    color: @accent@;
    border-color: @accent@;
}

QPushButton#testButton {
    background-color: @info@;
    color: @text_bright@;
    border: none;
    font-weight: bold;
    font-size: 14px;
}

QPushButton#testButton:hover {
    background-color: @info_hover@;
}

QPushButton#testButton:pressed {
    background-color: @info_pressed@;
}

QPushButton#resetButton {
    background-color: transparent;
    color: @text_muted@;
    border: 1px solid @border2@;
}

QPushButton#resetButton:hover {
    color: @text@;
    border-color: @border_hover@;
}

QTabWidget#settingsTabs::pane {
    border: 1px solid @border@;
    border-radius: 8px;
    background-color: @bg_panel@;
    top: -1px;
}

QTabWidget#settingsTabs QTabBar::tab {
    background-color: @header_section@;
    color: @text_muted@;
    border: 1px solid @border@;
    border-bottom: none;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    padding: 8px 16px;
    margin-right: 4px;
    font-weight: bold;
}

QTabWidget#settingsTabs QTabBar::tab:hover {
    background-color: @button_hover@;
    color: @text@;
}

QTabWidget#settingsTabs QTabBar::tab:selected {
    background-color: @accent@;
    color: @on_accent@;
    border-color: @accent@;
}
"""
