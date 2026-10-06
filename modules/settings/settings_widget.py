"""Widget de configuración de empresa y Hacienda (tarjetas agrupadas)."""

from PyQt6.QtCore import Qt
from PyQt6.QtPrintSupport import QPrinterInfo
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from utils.helpers import (
    ajustar_anchos_encabezado,
    EmptyStateTable,
    NoWheelComboBox,
)

from config import Config
from modules.promotions.promotion_dialog import PromotionDialog, describe_promotion
from modules.promotions.promotion_service import TYPE_LABELS
from ui.theme import (
    ACCENT_PRESETS,
    DENSITY_LABELS,
    DEFAULT_APPEARANCE,
    apply_theme,
    load_appearance,
    save_appearance,
)
from utils import secretos

CONFIG_KEYS = [
    "company_name",
    "company_id",
    "phone",
    "address",
    "activity_code",
    "environment",
    "username",
    "password",
    "pin",
    "certificate_path",
    "branch",
    "terminal",
    "consecutive_fe",
]

COLUMN_MAP = {
    "username": "username",
    "password": "password",
    "pin": "pin",
    "certificate_path": "certificate_path",
    "environment": "environment",
    "consecutive_fe": "consecutive_fe",
    "branch": "branch",
    "terminal": "terminal",
    "activity_code": "activity_code",
    "company_name": "company_name",
    "company_id": "company_id",
    "phone": "company_phone",
    "address": "company_address",
}


class SettingsWidget(QWidget):
    def __init__(self, services: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.services = services
        self.memory_config: dict = {}
        self._setup_ui()
        self._load_config()
        self._load_empresa_extra()

    # ---------- construcción de la UI ----------

    def _label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("formLabel")
        return label

    def _password_field(self) -> tuple[QLineEdit, QPushButton]:
        """Campo de contraseña con botón Mostrar/Ocultar."""
        field = QLineEdit()
        field.setEchoMode(QLineEdit.EchoMode.Password)
        toggle = QPushButton("Mostrar")
        toggle.setObjectName("toggleEye")
        toggle.setCheckable(True)
        toggle.setToolTip("Mostrar u ocultar el valor")

        def _toggle() -> None:
            visible = toggle.isChecked()
            field.setEchoMode(
                QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password)
            toggle.setText("Ocultar" if visible else "Mostrar")

        toggle.clicked.connect(_toggle)
        return field, toggle

    def _mini_field(self, text: str, widget: QWidget) -> QVBoxLayout:
        """Columna compacta: etiqueta pequeña arriba y campo debajo."""
        box = QVBoxLayout()
        box.setSpacing(4)
        box.addWidget(self._label(text))
        box.addWidget(widget)
        return box

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 16, 24, 16)
        outer.setSpacing(10)

        title = QLabel("Configuración")
        title.setObjectName("sectionTitle")
        outer.addWidget(title)
        subtitle = QLabel("Datos de la empresa y facturación electrónica (Hacienda)")
        subtitle.setObjectName("settingsSubtitle")
        outer.addWidget(subtitle)

        tabs = QTabWidget()
        tabs.setObjectName("settingsTabs")

        def _tab_page(max_width: int | None = 980
                      ) -> tuple[QScrollArea, QVBoxLayout]:
            page_scroll = QScrollArea()
            page_scroll.setWidgetResizable(True)
            page_scroll.setFrameShape(QFrame.Shape.NoFrame)
            page = QWidget()
            page_layout = QVBoxLayout(page)
            page_layout.setContentsMargins(4, 8, 4, 8)
            page_layout.setSpacing(16)
            if max_width:
                page.setMaximumWidth(max_width)
            page_scroll.setWidget(page)
            return page_scroll, page_layout

        company_page, company_page_layout = _tab_page()
        promo_page, promo_page_layout = _tab_page()
        hacienda_page, hacienda_page_layout = _tab_page()
        printer_page, printer_page_layout = _tab_page()
        appearance_page, appearance_page_layout = _tab_page(max_width=None)
        system_page, system_page_layout = _tab_page(max_width=None)

        # ---------- Tarjeta 1: Empresa ----------
        company_group = QGroupBox("Empresa")
        company_group.setObjectName("settingsGroup")
        company_form = QFormLayout(company_group)
        company_form.setContentsMargins(18, 14, 18, 14)
        company_form.setSpacing(12)

        self.company_name_input = QLineEdit()
        self.company_name_input.setPlaceholderText("Nombre comercial o razón social")
        self.company_id_input = QLineEdit()
        self.company_id_input.setPlaceholderText("3-101-123456")
        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("2222-0000")
        self.address_input = QLineEdit()
        self.address_input.setPlaceholderText("Provincia, cantón, distrito")
        self.activity_input = QLineEdit()
        self.activity_input.setPlaceholderText("Código de actividad económica (ej. 461201)")
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("Opcional: aparece en el ticket")
        self.iban_input = QLineEdit()
        self.iban_input.setPlaceholderText("Opcional: CR00 0000 0000 0000 0000 00")
        self.sinpe_input = QLineEdit()
        self.sinpe_input.setPlaceholderText("Opcional: 8888-8888")
        self.logo_input = QLineEdit()
        self.logo_input.setPlaceholderText("Opcional: PNG del encabezado del ticket")
        logo_button = QPushButton("Elegir…")
        logo_button.setObjectName("secondaryButton")
        logo_button.clicked.connect(self._pick_logo)
        logo_row = QWidget()
        logo_layout = QHBoxLayout(logo_row)
        logo_layout.setContentsMargins(0, 0, 0, 0)
        logo_layout.setSpacing(8)
        logo_layout.addWidget(self.logo_input, 1)
        logo_layout.addWidget(logo_button)

        company_form.addRow(self._label("Nombre de la empresa:"), self.company_name_input)
        company_form.addRow(self._label("Cédula jurídica:"), self.company_id_input)
        company_form.addRow(self._label("Teléfono:"), self.phone_input)
        company_form.addRow(self._label("Dirección:"), self.address_input)
        company_form.addRow(self._label("Actividad económica:"), self.activity_input)
        company_form.addRow(self._label("Correo electrónico:"), self.email_input)
        company_form.addRow(self._label("IBAN (transferencias):"), self.iban_input)
        company_form.addRow(self._label("SINPE Móvil:"), self.sinpe_input)
        company_form.addRow(self._label("Logo del ticket:"), logo_row)
        company_page_layout.addWidget(company_group)

        # ---------- Tarjeta 2: Promociones y descuentos ----------
        promo_group = QGroupBox("Promociones y descuentos")
        promo_group.setObjectName("settingsGroup")
        promo_layout = QVBoxLayout(promo_group)
        promo_layout.setContentsMargins(18, 14, 18, 14)
        promo_layout.setSpacing(10)

        promo_buttons = QHBoxLayout()
        new_promo = QPushButton("Nueva promoción")
        new_promo.setObjectName("primaryButton")
        new_promo.clicked.connect(self._new_promotion)
        edit_promo = QPushButton("Editar")
        edit_promo.clicked.connect(self._edit_promotion)
        toggle_promo = QPushButton("Activar/Desactivar")
        toggle_promo.setObjectName("secondaryButton")
        toggle_promo.clicked.connect(self._toggle_promotion)
        delete_promo = QPushButton("Eliminar")
        delete_promo.setObjectName("dangerButton")
        delete_promo.clicked.connect(self._delete_promotion)
        promo_buttons.addWidget(new_promo)
        promo_buttons.addWidget(edit_promo)
        promo_buttons.addWidget(toggle_promo)
        promo_buttons.addWidget(delete_promo)
        promo_buttons.addStretch(1)
        promo_layout.addLayout(promo_buttons)

        self.promotions_table = EmptyStateTable(
            "Sin promociones configuradas.", 0, 4)
        self.promotions_table.setHorizontalHeaderLabels(
            ["Nombre", "Tipo", "Detalle", "Estado"])
        self.promotions_table.horizontalHeader().setObjectName("tableHeader")
        self.promotions_table.verticalHeader().setVisible(False)
        self.promotions_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self.promotions_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self.promotions_table.setAlternatingRowColors(True)
        self.promotions_table.setMaximumHeight(220)
        self.promotions_table.doubleClicked.connect(self._edit_promotion)
        ajustar_anchos_encabezado(
            self.promotions_table, [210, 170, 420, 110])
        promo_layout.addWidget(self.promotions_table)

        promo_hint = QLabel(
            "Conjuntos (2 productos), volumen por cantidad, descuento por método "
            "de pago y meses sin intereses para ventas a crédito. Se aplican "
            "solos en el carrito.")
        promo_hint.setObjectName("settingsHint")
        promo_hint.setWordWrap(True)
        promo_layout.addWidget(promo_hint)
        promo_page_layout.addWidget(promo_group)

        # ---------- Tarjeta 3: Hacienda ----------
        hacienda_group = QGroupBox("Hacienda · Facturación electrónica")
        hacienda_group.setObjectName("settingsGroup")
        hacienda_form = QFormLayout(hacienda_group)
        hacienda_form.setContentsMargins(18, 14, 18, 14)
        hacienda_form.setSpacing(12)

        self.environment_combo = NoWheelComboBox()
        self.environment_combo.addItem("Sandbox (pruebas)", "sandbox")
        self.environment_combo.addItem("Producción", "produccion")
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Usuario del portal de Hacienda")
        self.password_input, password_toggle = self._password_field()
        self.pin_input, pin_toggle = self._password_field()
        self.pin_input.setToolTip("PIN del certificado de firma digital")

        certificate_row = QHBoxLayout()
        certificate_row.setSpacing(6)
        self.certificate_input = QLineEdit()
        self.certificate_input.setReadOnly(True)
        self.certificate_input.setPlaceholderText("Seleccione el archivo .p12")
        browse_button = QPushButton("Buscar…")
        browse_button.clicked.connect(self._browse_certificate)
        certificate_row.addWidget(self.certificate_input, 1)
        certificate_row.addWidget(browse_button)

        self.branch_input = QLineEdit()
        self.branch_input.setPlaceholderText("001")
        self.terminal_input = QLineEdit()
        self.terminal_input.setPlaceholderText("001")
        self.consecutive_input = QLineEdit()
        self.consecutive_input.setPlaceholderText("00000001")

        hacienda_form.addRow(self._label("Ambiente:"), self.environment_combo)
        hacienda_form.addRow(self._label("Usuario Hacienda:"), self.username_input)
        hacienda_form.addRow(self._label("Contraseña Hacienda:"),
                             self._field_row(self.password_input, password_toggle))
        hacienda_form.addRow(self._label("PIN del certificado:"),
                             self._field_row(self.pin_input, pin_toggle))
        hacienda_form.addRow(self._label("Certificado (.p12):"), certificate_row)
        certificate_hint = QLabel("Archivo .p12 emitido por el Ministerio de Hacienda")
        certificate_hint.setObjectName("settingsHint")
        hacienda_form.addRow("", certificate_hint)

        numbering_row = QHBoxLayout()
        numbering_row.setSpacing(10)
        numbering_row.addLayout(self._mini_field("Sucursal", self.branch_input), 1)
        numbering_row.addLayout(self._mini_field("Terminal", self.terminal_input), 1)
        numbering_row.addLayout(self._mini_field("Consecutivo FE", self.consecutive_input), 1)
        hacienda_form.addRow(self._label("Numeración:"), numbering_row)
        hacienda_page_layout.addWidget(hacienda_group)

        # ---------- Tarjeta 3: Moneda ----------
        currency_group = QGroupBox("Moneda y Tipo de Cambio")
        currency_group.setObjectName("settingsGroup")
        currency_form = QFormLayout(currency_group)
        currency_form.setContentsMargins(18, 14, 18, 14)
        currency_form.setSpacing(12)

        self.exchange_rate_input = QLineEdit()
        self.exchange_rate_input.setPlaceholderText("520.00")
        self.exchange_rate_input.setToolTip("Tipo de cambio:₡ por $1 USD")
        self.exchange_rate_date_label = QLabel("")
        self.exchange_rate_date_label.setObjectName("settingsHint")

        update_rate_button = QPushButton("Actualizar tipo de cambio")
        update_rate_button.setObjectName("primaryButton")
        update_rate_button.clicked.connect(self._update_exchange_rate)

        currency_form.addRow(self._label("Tipo de cambio (₡/$):"), self.exchange_rate_input)
        currency_form.addRow(self._label("Última actualización:"), self.exchange_rate_date_label)
        currency_form.addRow("", update_rate_button)
        company_page_layout.addWidget(currency_group)

        # ---------- Tarjeta 4: Impresora ----------
        printer_group = QGroupBox("Impresora de tickets")
        printer_group.setObjectName("settingsGroup")
        printer_form = QFormLayout(printer_group)
        printer_form.setContentsMargins(18, 14, 18, 14)
        printer_form.setSpacing(12)

        self.printer_combo = NoWheelComboBox()
        self.printer_combo.addItem("Predeterminada de Windows", "")
        for _printer in QPrinterInfo.availablePrinters():
            self.printer_combo.addItem(_printer.printerName(), _printer.printerName())

        self.paper_combo = NoWheelComboBox()
        from modules.documentos.ticket import PAPER_MODES
        for clave, etiqueta in PAPER_MODES.items():
            self.paper_combo.addItem(etiqueta, clave)
        self.paper_combo.setToolTip(
            "Windows: usa el papel ya configurado en el driver.\n"
            "Etiqueta: imprime todo el ticket en una etiqueta.")

        self.print_dialog_check = QCheckBox(
            "Mostrar menú de impresión antes de imprimir tickets de venta")
        self.print_dialog_check.setToolTip(
            "Si está activado, cada ticket abre el menú de Windows para "
            "elegir la impresora o cancelar. Por defecto imprime directo.")

        self.a4_combo = NoWheelComboBox()
        self.a4_combo.addItem("Predeterminada de Windows", "")
        for _printer in QPrinterInfo.availablePrinters():
            self.a4_combo.addItem(_printer.printerName(), _printer.printerName())
        self.a4_combo.setToolTip(
            "Impresora de hojas para la factura A4 en PDF.\n"
            "La térmica de 80mm no imprime la A4: si no hay una impresora A4 "
            "configurada, solo se guarda el PDF.")

        test_printer_button = QPushButton("Vista previa / Probar impresión")
        test_printer_button.setObjectName("primaryButton")
        test_printer_button.clicked.connect(self._test_printer)

        format_button = QPushButton("Formato del ticket…")
        format_button.setObjectName("secondaryButton")
        format_button.setToolTip(
            "Diseñá el tiquete de 80 mm (bloques, textos, letra y papel) con "
            "vista previa en vivo.")
        format_button.clicked.connect(self._open_ticket_format_dialog)

        test_a4_button = QPushButton("Probar factura A4")
        test_a4_button.setObjectName("secondaryButton")
        test_a4_button.setToolTip(
            "Imprime una factura A4 de ejemplo en la impresora de hojas "
            "elegida (la térmica de 80mm no imprime A4).")
        test_a4_button.clicked.connect(self._test_a4)

        printer_hint = QLabel("Se usa al imprimir tickets de venta (térmica 80mm)")
        printer_hint.setObjectName("settingsHint")
        printer_form.addRow(self._label("Impresora de tickets:"), self.printer_combo)
        printer_form.addRow(self._label("Papel del ticket:"), self.paper_combo)
        printer_form.addRow(self._label("Impresora para facturas A4:"), self.a4_combo)
        printer_form.addRow("", self.print_dialog_check)
        printer_form.addRow("", test_printer_button)
        printer_form.addRow("", format_button)
        printer_form.addRow("", test_a4_button)
        printer_form.addRow("", printer_hint)
        printer_page_layout.addWidget(printer_group)

        # ---------- Tarjeta 5: Documentos ----------
        docs_group = QGroupBox("Carpeta de documentos (XML + PDF)")
        docs_group.setObjectName("settingsGroup")
        docs_form = QFormLayout(docs_group)
        docs_form.setContentsMargins(18, 14, 18, 14)
        docs_form.setSpacing(12)

        self.docs_path_label = QLabel("")
        self.docs_path_label.setWordWrap(True)
        self.docs_path_label.setObjectName("settingsHint")

        open_docs_button = QPushButton("Abrir carpeta")
        open_docs_button.setObjectName("primaryButton")
        open_docs_button.clicked.connect(self._open_docs_folder)

        test_docs_button = QPushButton("Probar carpeta")
        test_docs_button.setObjectName("secondaryButton")
        test_docs_button.clicked.connect(self._test_docs_folder)

        docs_hint = QLabel(
            "Ruta definida en config.ini (DOCS_PATH). Si es una carpeta compartida "
            "en red (\\\\SERVIDOR\\documentos), todas las cajas archivan en el mismo "
            "lugar. Si no responde, se guarda en Documentos\\PosLaLoma.")
        docs_hint.setObjectName("settingsHint")
        docs_hint.setWordWrap(True)
        docs_form.addRow(self._label("Carpeta actual:"), self.docs_path_label)
        docs_form.addRow("", open_docs_button)
        docs_form.addRow("", test_docs_button)
        docs_form.addRow("", docs_hint)
        printer_page_layout.addWidget(docs_group)

        # ---------- Sistema en dos columnas ----------
        system_columns = QHBoxLayout()
        system_columns.setSpacing(16)
        system_left = QVBoxLayout()
        system_left.setSpacing(16)
        system_right = QVBoxLayout()
        system_right.setSpacing(16)
        system_columns.addLayout(system_left, 1)
        system_columns.addLayout(system_right, 1)
        system_page_layout.addLayout(system_columns)
        system_page_layout.addStretch(1)

        # ---------- Tarjeta 6: Actualizaciones ----------
        update_group = QGroupBox("Actualizaciones (red local)")
        update_group.setObjectName("settingsGroup")
        update_form = QFormLayout(update_group)
        update_form.setContentsMargins(18, 14, 18, 14)
        update_form.setSpacing(12)

        self.version_label = QLabel("")
        self.version_label.setObjectName("settingsHint")
        check_update_button = QPushButton("Buscar actualizaciones")
        check_update_button.setObjectName("primaryButton")
        check_update_button.clicked.connect(self._check_updates)

        update_hint = QLabel(
            "El servidor revisa la carpeta de updates y las cajas descargan e "
            "instalan la versión nueva automáticamente (sin internet).")
        update_hint.setObjectName("settingsHint")
        update_hint.setWordWrap(True)
        update_form.addRow(self._label("Versión instalada:"), self.version_label)
        update_form.addRow("", check_update_button)
        update_form.addRow("", update_hint)
        system_left.addWidget(update_group)

        # ---------- Tarjeta 7: Diagnóstico ----------
        diag_group = QGroupBox("Diagnóstico de la instalación")
        diag_group.setObjectName("settingsGroup")
        diag_form = QFormLayout(diag_group)
        diag_form.setContentsMargins(18, 14, 18, 14)
        diag_form.setSpacing(12)

        diag_button = QPushButton("Probar instalación")
        diag_button.setObjectName("primaryButton")
        diag_button.clicked.connect(self._run_diagnostico)
        diag_hint = QLabel(
            "Revisa Windows, permisos, disco, puerto del servidor, impresoras y "
            "la base de datos. Copie el reporte si algo falla.")
        diag_hint.setObjectName("settingsHint")
        diag_hint.setWordWrap(True)
        diag_form.addRow("", diag_button)
        diag_form.addRow("", diag_hint)
        system_left.addWidget(diag_group)

        # ---------- Tarjeta 8: Estado de la estación (solo lectura) ----------
        status_group = QGroupBox("Estado de la estación")
        status_group.setObjectName("settingsGroup")
        status_form = QFormLayout(status_group)
        status_form.setContentsMargins(18, 14, 18, 14)
        status_form.setSpacing(12)

        self.station_value = QLabel(getattr(Config, "STATION", "CAJA1"))
        self.station_value.setObjectName("statusValue")
        self.mode_value = QLabel(
            "Servidor central" if Config.MODE == "server" else "Local (una PC)")
        self.mode_value.setObjectName("statusValue")
        self.server_value = QLabel(Config.SERVER_URL)
        self.server_value.setObjectName("statusValue")
        self.server_value.setWordWrap(True)
        self.server_value.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)

        status_hint = QLabel(
            "Estos datos vienen de config.ini y se fijan antes de iniciar el "
            "POS. Para cambiarlos edite config.ini en esta PC y reinicie.")
        status_hint.setObjectName("settingsHint")
        status_hint.setWordWrap(True)
        status_form.addRow(self._label("Estación:"), self.station_value)
        status_form.addRow(self._label("Modo:"), self.mode_value)
        status_form.addRow(self._label("Servidor:"), self.server_value)
        status_form.addRow("", status_hint)
        system_right.addWidget(status_group)
        system_right.addStretch(1)

        # ---------- Tarjeta 9: Apariencia ----------
        theme_group = QGroupBox("Tema")
        theme_group.setObjectName("settingsGroup")
        theme_form = QFormLayout(theme_group)
        theme_form.setContentsMargins(18, 14, 18, 14)
        theme_form.setSpacing(12)

        self.appearance_theme_combo = NoWheelComboBox()
        self.appearance_theme_combo.addItem("Oscuro", "dark")
        self.appearance_theme_combo.addItem("Claro", "light")
        theme_hint = QLabel(
            "La apariencia se guarda en el servidor y se comparte con todas "
            "las cajas.")
        theme_hint.setObjectName("settingsHint")
        theme_hint.setWordWrap(True)
        theme_form.addRow(self._label("Tema de la interfaz:"),
                          self.appearance_theme_combo)
        theme_form.addRow("", theme_hint)
        appearance_page_layout.addWidget(theme_group)

        accent_group = QGroupBox("Color de acento")
        accent_group.setObjectName("settingsGroup")
        accent_layout = QVBoxLayout(accent_group)
        accent_layout.setContentsMargins(18, 14, 18, 14)
        accent_layout.setSpacing(10)

        self._selected_accent = DEFAULT_APPEARANCE["accent"]
        self.accent_buttons: dict[str, QPushButton] = {}
        swatch_row = QHBoxLayout()
        swatch_row.setSpacing(10)
        for nombre, color in ACCENT_PRESETS:
            swatch = QPushButton()
            swatch.setFixedSize(34, 34)
            swatch.setToolTip(nombre)
            swatch.clicked.connect(
                lambda _checked=False, col=color: self._pick_accent(col))
            self.accent_buttons[color] = swatch
            swatch_row.addWidget(swatch)
        other_button = QPushButton("Otro color…")
        other_button.setObjectName("secondaryButton")
        other_button.clicked.connect(self._pick_custom_accent)
        swatch_row.addWidget(other_button)
        swatch_row.addStretch(1)
        accent_layout.addLayout(swatch_row)
        accent_hint = QLabel(
            "Se usa en botones principales, selección y resaltados.")
        accent_hint.setObjectName("settingsHint")
        accent_layout.addWidget(accent_hint)
        appearance_page_layout.addWidget(accent_group)

        size_group = QGroupBox("Tamaño y densidad")
        size_group.setObjectName("settingsGroup")
        size_form = QFormLayout(size_group)
        size_form.setContentsMargins(18, 14, 18, 14)
        size_form.setSpacing(12)

        font_row = QHBoxLayout()
        font_row.setSpacing(10)
        self.appearance_font_slider = QSlider(Qt.Orientation.Horizontal)
        self.appearance_font_slider.setRange(85, 135)
        self.appearance_font_slider.setSingleStep(5)
        self.appearance_font_slider.setPageStep(5)
        self.appearance_font_slider.setValue(100)
        self.appearance_font_label = QLabel("100%")
        self.appearance_font_label.setObjectName("statusValue")
        self.appearance_font_label.setMinimumWidth(52)
        font_row.addWidget(self.appearance_font_slider, 1)
        font_row.addWidget(self.appearance_font_label)

        self.appearance_density_combo = NoWheelComboBox()
        for clave, etiqueta in DENSITY_LABELS.items():
            self.appearance_density_combo.addItem(etiqueta, clave)

        size_form.addRow(self._label("Tamaño del texto:"), font_row)
        size_form.addRow(self._label("Densidad:"),
                         self.appearance_density_combo)
        appearance_page_layout.addWidget(size_group)

        preview_group = QGroupBox("Vista previa")
        preview_group.setObjectName("settingsGroup")
        preview_layout = QVBoxLayout(preview_group)
        preview_layout.setContentsMargins(18, 14, 18, 14)
        preview_layout.setSpacing(10)
        preview = QWidget()
        preview.setObjectName("appearancePreview")
        preview_box = QVBoxLayout(preview)
        preview_box.setContentsMargins(14, 12, 14, 12)
        preview_box.setSpacing(8)
        preview_title = QLabel("Texto de ejemplo")
        preview_title.setObjectName("sectionTitle")
        preview_hint = QLabel("Así se verá la interfaz de la caja.")
        preview_hint.setObjectName("settingsHint")
        preview_input = QLineEdit()
        preview_input.setPlaceholderText("Campo de texto")
        preview_primary = QPushButton("Botón principal")
        preview_primary.setObjectName("primaryButton")
        preview_secondary = QPushButton("Botón secundario")
        preview_secondary.setObjectName("secondaryButton")
        preview_buttons = QHBoxLayout()
        preview_buttons.setSpacing(10)
        preview_buttons.addWidget(preview_primary)
        preview_buttons.addWidget(preview_secondary)
        preview_buttons.addStretch(1)
        preview_box.addWidget(preview_title)
        preview_box.addWidget(preview_hint)
        preview_box.addWidget(preview_input)
        preview_box.addLayout(preview_buttons)
        preview_layout.addWidget(preview)
        appearance_page_layout.addWidget(preview_group)

        appearance_actions = QHBoxLayout()
        appearance_actions.setSpacing(10)
        reset_appearance = QPushButton("Restablecer apariencia")
        reset_appearance.setObjectName("resetButton")
        reset_appearance.clicked.connect(self._reset_appearance)
        appearance_actions.addWidget(reset_appearance)
        appearance_actions.addStretch(1)
        appearance_page_layout.addLayout(appearance_actions)
        appearance_page_layout.addStretch(1)

        # ---------- Acciones ----------
        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        save_button = QPushButton("Guardar")
        save_button.setObjectName("primaryButton")
        save_button.clicked.connect(self._save)
        test_button = QPushButton("Probar Conexión")
        test_button.setObjectName("testButton")
        test_button.clicked.connect(self._test_connection)
        reset_button = QPushButton("Restablecer")
        reset_button.setObjectName("resetButton")
        reset_button.setToolTip("Volver a cargar los valores guardados")
        reset_button.clicked.connect(self._restore)
        buttons.addWidget(save_button)
        buttons.addWidget(test_button)
        buttons.addWidget(reset_button)
        buttons.addStretch(1)

        tabs.addTab(company_page, "Empresa")
        tabs.addTab(promo_page, "Promociones")
        tabs.addTab(hacienda_page, "Hacienda")
        tabs.addTab(printer_page, "Impresora y docs")
        tabs.addTab(appearance_page, "Apariencia")
        tabs.addTab(system_page, "Sistema")
        outer.addWidget(tabs, 1)
        outer.addLayout(buttons)

        self.appearance_theme_combo.currentIndexChanged.connect(
            self._preview_appearance)
        self.appearance_density_combo.currentIndexChanged.connect(
            self._preview_appearance)
        self.appearance_font_slider.valueChanged.connect(
            self._on_font_scale_changed)
        self._refresh_swatches()

    def _field_row(self, field: QLineEdit, toggle: QPushButton) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(field, 1)
        row.addWidget(toggle)
        return row

    def _restore(self) -> None:
        self._load_config()
        QMessageBox.information(self, "Configuración",
                                "Se restauraron los valores guardados.")

    # ---------- apariencia ----------

    def _appearance_values(self) -> dict:
        return {
            "theme": self.appearance_theme_combo.currentData() or "dark",
            "accent": self._selected_accent,
            "font_scale": self.appearance_font_slider.value() / 100.0,
            "density": self.appearance_density_combo.currentData() or "normal",
        }

    def _apply_appearance_controls(self, settings: dict) -> None:
        index = self.appearance_theme_combo.findData(
            settings.get("theme", "dark"))
        if index >= 0:
            self.appearance_theme_combo.blockSignals(True)
            self.appearance_theme_combo.setCurrentIndex(index)
            self.appearance_theme_combo.blockSignals(False)
        self._selected_accent = (settings.get("accent")
                                 or DEFAULT_APPEARANCE["accent"])
        try:
            escala = int(round(float(settings.get("font_scale", 1.0)) * 100))
        except (TypeError, ValueError):
            escala = 100
        self.appearance_font_slider.blockSignals(True)
        self.appearance_font_slider.setValue(max(85, min(135, escala)))
        self.appearance_font_slider.blockSignals(False)
        self.appearance_font_label.setText(
            f"{self.appearance_font_slider.value()}%")
        index = self.appearance_density_combo.findData(
            settings.get("density", "normal"))
        if index >= 0:
            self.appearance_density_combo.blockSignals(True)
            self.appearance_density_combo.setCurrentIndex(index)
            self.appearance_density_combo.blockSignals(False)
        self._refresh_swatches()

    def _load_appearance(self) -> None:
        try:
            settings = load_appearance(self.services.get("db"))
        except Exception:
            settings = dict(DEFAULT_APPEARANCE)
        self._apply_appearance_controls(settings)

    def _pick_accent(self, color: str) -> None:
        self._selected_accent = color
        self._refresh_swatches()
        self._preview_appearance()

    def _pick_custom_accent(self) -> None:
        from PyQt6.QtGui import QColor
        from PyQt6.QtWidgets import QColorDialog
        color = QColorDialog.getColor(
            QColor(self._selected_accent), self, "Color de acento")
        if color.isValid():
            self._pick_accent(color.name())

    def _refresh_swatches(self) -> None:
        for color, button in self.accent_buttons.items():
            selected = color.lower() == str(self._selected_accent).lower()
            borde = ("3px solid #ffffff" if selected
                     else "1px solid rgba(0, 0, 0, 0.25)")
            try:
                r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
                luminancia = 0.299 * r + 0.587 * g + 0.114 * b
                tinta = "#0e1a12" if luminancia > 140 else "#ffffff"
            except Exception:
                tinta = "#ffffff"
            button.setText("✓" if selected else "")
            button.setStyleSheet(
                f"background-color: {color}; border: {borde}; "
                f"border-radius: 8px; color: {tinta}; font-weight: bold;")

    def _on_font_scale_changed(self, value: int) -> None:
        self.appearance_font_label.setText(f"{value}%")
        self._preview_appearance()

    def _preview_appearance(self, *_args) -> None:
        app = QApplication.instance()
        if app is not None:
            apply_theme(app, self._appearance_values())

    def _reset_appearance(self) -> None:
        self._apply_appearance_controls(dict(DEFAULT_APPEARANCE))
        self._preview_appearance()
        QMessageBox.information(
            self, "Apariencia",
            "Se restableció la apariencia. Pulse «Guardar» para aplicarla a "
            "todas las cajas.")

    def _save_appearance(self) -> None:
        save_appearance(self.services.get("db"), self._appearance_values())

    def _browse_certificate(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar certificado",
            "",
            "Certificados (*.p12 *.pem *.cer);;Todos los archivos (*)",
        )
        if path:
            self.certificate_input.setText(path)

    def _config_values(self) -> dict:
        return {
            "company_name": self.company_name_input.text().strip(),
            "company_id": self.company_id_input.text().strip(),
            "phone": self.phone_input.text().strip(),
            "address": self.address_input.text().strip(),
            "activity_code": self.activity_input.text().strip(),
            "environment": self.environment_combo.currentData(),
            "username": self.username_input.text().strip(),
            "password": self.password_input.text().strip(),
            "pin": self.pin_input.text().strip(),
            "certificate_path": self.certificate_input.text().strip(),
            "branch": self.branch_input.text().strip(),
            "terminal": self.terminal_input.text().strip(),
            "consecutive_fe": self.consecutive_input.text().strip(),
        }

    def _apply_config(self, config: dict) -> None:
        config = secretos.descifrar_campos(config)
        self.company_name_input.setText(config.get("company_name", ""))
        self.company_id_input.setText(config.get("company_id", ""))
        self.phone_input.setText(config.get("phone", ""))
        self.address_input.setText(config.get("address", ""))
        self.activity_input.setText(config.get("activity_code", ""))
        index = self.environment_combo.findData(config.get("environment", "sandbox"))
        if index >= 0:
            self.environment_combo.setCurrentIndex(index)
        self.username_input.setText(config.get("username", ""))
        self.password_input.setText(config.get("password", ""))
        self.pin_input.setText(config.get("pin", ""))
        self.certificate_input.setText(config.get("certificate_path", ""))
        self.branch_input.setText(config.get("branch", ""))
        self.terminal_input.setText(config.get("terminal", ""))
        self.consecutive_input.setText(config.get("consecutive_fe", ""))
        self._load_exchange_rate()
        self._load_printer()
        self._load_docs_path()
        self._load_version()

    def _load_config(self) -> None:
        self._refresh_promotions()
        db = self.services.get("db")
        config_applied = False
        if db is not None:
            try:
                rows = db.execute_query("SELECT * FROM hacienda_config WHERE id = 1") or []
                if rows:
                    row = {str(key): value for key, value in rows[0].items()}
                    config = {key: row.get(column, "") for key, column in COLUMN_MAP.items()}
                    self._apply_config(config)
                    config_applied = True
            except Exception:
                pass
        if not config_applied and self.memory_config:
            self._apply_config(self.memory_config)
        self._load_appearance()

    def _save(self) -> None:
        values = self._config_values()
        db = self.services.get("db")
        if db is not None:
            # Los secretos nunca se guardan en texto plano: se conserva el
            # valor cifrado existente en el INSERT y luego se piden los nuevos
            # a `guardar_secretos` (el servidor los cifra con su DPAPI).
            existentes = {}
            try:
                rows = db.execute_query(
                    "SELECT password, pin FROM hacienda_config WHERE id = 1")
                if rows:
                    existentes = {clave: (rows[0].get(clave) or "")
                                  for clave in ("password", "pin")}
            except Exception:
                pass
            nuevos = {clave: values.get(clave, "") for clave in ("password", "pin")}
            values["password"] = existentes.get("password", "")
            values["pin"] = existentes.get("pin", "")
            columns = [COLUMN_MAP[key] for key in values]
            placeholders = ", ".join("?" for _ in columns)
            sql = (
                f"INSERT OR REPLACE INTO hacienda_config (id, {', '.join(columns)}) "
                f"VALUES (1, {placeholders})"
            )
            try:
                db.execute_insert(sql, tuple(values[key] for key in values))
                if hasattr(db, "guardar_secretos"):
                    db.guardar_secretos(password=nuevos.get("password", ""),
                                        pin=nuevos.get("pin", ""))
                self._save_extras()
                QMessageBox.information(self, "Configuración", "Configuración guardada correctamente.")
                return
            except Exception as exc:
                try:
                    for key, value in values.items():
                        db.execute_insert(
                            "INSERT OR REPLACE INTO hacienda_config (key, value) VALUES (?, ?)",
                            (key, str(value)),
                        )
                    self._save_extras()
                    QMessageBox.information(self, "Configuración", "Configuración guardada correctamente.")
                    return
                except Exception:
                    self.memory_config = values
                    QMessageBox.warning(
                        self,
                        "Configuración",
                        f"No se pudo guardar en la base de datos:\n{exc}\n\nConfiguración guardada en memoria.",
                    )
                    return
        self.memory_config = values
        QMessageBox.information(
            self,
            "Configuración",
            "No hay base de datos disponible. Configuración guardada en memoria.",
        )

    def _save_printer(self) -> None:
        """Guarda impresora, papel y preferencia de diálogo en app_config."""
        db = self.services.get("db")
        if db is None:
            return
        try:
            from modules.documentos.pdf_factura import save_a4_printer
            from modules.documentos.ticket import (
                save_paper_mode,
                save_printer_name,
                save_show_dialog,
            )
            save_printer_name(db, self.printer_combo.currentData() or "")
            save_paper_mode(db, self.paper_combo.currentData() or "")
            save_show_dialog(db, self.print_dialog_check.isChecked())
            save_a4_printer(db, self.a4_combo.currentData() or "")
        except Exception:
            pass

    def _save_extras(self) -> None:
        """Guarda impresora, papel, A4, datos extra de empresa y apariencia."""
        self._save_printer()
        self._save_empresa_extra()
        self._save_appearance()

    def _save_empresa_extra(self) -> None:
        """Guarda correo, IBAN, SINPE y logo del ticket (app_config)."""
        db = self.services.get("db")
        if db is None:
            return
        try:
            from modules.documentos.xml_factura import guardar_empresa_extra

            guardar_empresa_extra(
                db,
                email=self.email_input.text().strip(),
                iban=self.iban_input.text().strip(),
                sinpe=self.sinpe_input.text().strip(),
                logo=self.logo_input.text().strip())
        except Exception:
            pass

    def _load_empresa_extra(self) -> None:
        """Carga correo, IBAN, SINPE y logo desde app_config."""
        db = self.services.get("db")
        if db is None:
            return
        try:
            from modules.documentos.xml_factura import cargar_empresa

            datos = cargar_empresa(db)
            self.email_input.setText(datos.get("email", ""))
            self.iban_input.setText(datos.get("iban", ""))
            self.sinpe_input.setText(datos.get("sinpe", ""))
            self.logo_input.setText(datos.get("logo", ""))
        except Exception:
            pass

    def _pick_logo(self) -> None:
        """Elige el PNG del encabezado del ticket."""
        ruta, _ = QFileDialog.getOpenFileName(
            self, "Logo del ticket", "",
            "Imágenes (*.png *.jpg *.jpeg);;Todos los archivos (*)")
        if ruta:
            self.logo_input.setText(ruta)

    def _test_connection(self) -> None:
        QMessageBox.information(self, "Prueba de conexión", "Verificando conexión con Hacienda…")
        try:
            ok = bool(self.services["hacienda"].check_connection())
        except Exception as exc:
            QMessageBox.warning(self, "Prueba de conexión", f"Error al verificar la conexión:\n{exc}")
            return
        if ok:
            QMessageBox.information(self, "Prueba de conexión", "Conexión con Hacienda establecida correctamente.")
        else:
            QMessageBox.warning(self, "Prueba de conexión", "No se pudo conectar con los servicios de Hacienda.")

    def _run_diagnostico(self) -> None:
        """Ejecuta el diagnóstico de instalación y muestra el resultado."""
        try:
            from utils.diagnostico import recolectar
            from ui.error_dialog import mostrar_diagnostico
            checks = recolectar()
        except Exception as exc:
            QMessageBox.warning(self, "Diagnóstico",
                                f"No se pudo ejecutar el diagnóstico:\n{exc}")
            return
        mostrar_diagnostico(self, checks)

    # ---------- promociones ----------

    def _promotions_service(self):
        return self.services.get("promotions")

    def _refresh_promotions(self) -> None:
        service = self._promotions_service()
        table = self.promotions_table
        if service is None:
            table.setRowCount(0)
            return
        try:
            promotions = service.get_all()
            products = {p.id: p for p in self.services["product"].get_all()}
        except Exception:
            promotions, products = [], {}
        table.setRowCount(len(promotions))
        for row, promo in enumerate(promotions):
            values = [
                promo.name,
                TYPE_LABELS.get(promo.type, promo.type),
                describe_promotion(promo, products),
                "Activa" if promo.active else "Inactiva",
            ]
            for col, val in enumerate(values):
                item = QTableWidgetItem(str(val))
                if col == 3:
                    item.setForeground(Qt.GlobalColor.green if promo.active
                                       else Qt.GlobalColor.gray)
                table.setItem(row, col, item)
            table.item(row, 0).setData(Qt.ItemDataRole.UserRole, promo)
        table.resizeRowsToContents()

    def _selected_promotion(self):
        row = self.promotions_table.currentRow()
        if row < 0:
            return None
        item = self.promotions_table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _new_promotion(self) -> None:
        service = self._promotions_service()
        if service is None:
            return
        products = self.services["product"].get_all()
        dialog = PromotionDialog(service, products=products, parent=self)
        if dialog.exec() and dialog.saved:
            self._refresh_promotions()

    def _edit_promotion(self) -> None:
        promo = self._selected_promotion()
        service = self._promotions_service()
        if promo is None or service is None:
            QMessageBox.information(self, "Promociones",
                                    "Seleccione una promoción.")
            return
        products = self.services["product"].get_all()
        dialog = PromotionDialog(service, promotion=promo, products=products,
                                 parent=self)
        if dialog.exec() and dialog.saved:
            self._refresh_promotions()

    def _toggle_promotion(self) -> None:
        promo = self._selected_promotion()
        service = self._promotions_service()
        if promo is None or service is None:
            QMessageBox.information(self, "Promociones",
                                    "Seleccione una promoción.")
            return
        service.set_active(promo.id, not bool(promo.active))
        self._refresh_promotions()

    def _delete_promotion(self) -> None:
        promo = self._selected_promotion()
        service = self._promotions_service()
        if promo is None or service is None:
            QMessageBox.information(self, "Promociones",
                                    "Seleccione una promoción.")
            return
        answer = QMessageBox.question(
            self, "Eliminar promoción",
            f"¿Eliminar la promoción '{promo.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        service.delete(promo.id)
        self._refresh_promotions()

    def _load_exchange_rate(self) -> None:
        """Carga el tipo de cambio actual de la base de datos."""
        db = self.services.get("db")
        if db is None:
            return
        try:
            from network.exchange_rate import get_exchange_rate_from_db
            rate, date_str = get_exchange_rate_from_db(db)
            self.exchange_rate_input.setText(f"{rate:.2f}")
            if date_str:
                self.exchange_rate_date_label.setText(date_str)
            else:
                self.exchange_rate_date_label.setText("Sin actualizar automáticamente")
        except Exception:
            self.exchange_rate_input.setText("520.00")
            self.exchange_rate_date_label.setText("Error al cargar")

    def _update_exchange_rate(self) -> None:
        """Actualiza el tipo de cambio desde la API o desde el campo manual."""
        db = self.services.get("db")
        if db is None:
            QMessageBox.warning(self, "Moneda", "No hay base de datos disponible.")
            return

        # Intentar actualizar desde la API
        try:
            from network.exchange_rate import update_exchange_rate, save_exchange_rate
            rate, date_str, updated = update_exchange_rate(db)
            self.exchange_rate_input.setText(f"{rate:.2f}")
            if date_str:
                self.exchange_rate_date_label.setText(date_str)
            if updated:
                QMessageBox.information(
                    self, "Moneda",
                    f"Tipo de cambio actualizado desde la API:₡{rate:.2f} por $1 USD"
                )
            else:
                QMessageBox.warning(
                    self, "Moneda",
                    "No se pudo conectar con la API de tipo de cambio.\n"
                    f"Se mantiene el último valor guardado:₡{rate:.2f} por $1 USD.\n"
                    "Verifique la conexión a internet e intente de nuevo.",
                )
        except Exception as exc:
            # Si la API falla, guardar el valor manual
            try:
                manual_rate = float(self.exchange_rate_input.text().replace(",", "."))
                if manual_rate > 0:
                    from datetime import datetime
                    save_exchange_rate(db, manual_rate)
                    self.exchange_rate_date_label.setText(
                        datetime.now().strftime("%Y-%m-%d %H:%M") + " (manual)")
                    QMessageBox.information(
                        self, "Moneda",
                        f"Tipo de cambio guardado:₡{manual_rate:.2f} por $1 USD"
                    )
                else:
                    QMessageBox.warning(self, "Moneda", "Ingrese un tipo de cambio válido.")
            except Exception as e:
                QMessageBox.warning(
                    self, "Moneda",
                    f"No se pudo guardar el tipo de cambio:\n{e}\n"
                    "Verifique que el servidor del POS esté reiniciado.",
                )

    def _load_printer(self) -> None:
        """Carga impresora, papel y preferencia de diálogo de la base."""
        db = self.services.get("db")
        if db is None:
            return
        try:
            from modules.documentos.pdf_factura import get_a4_printer
            from modules.documentos.ticket import (
                get_paper_mode,
                get_printer_name,
                get_show_dialog,
            )
            name = get_printer_name(db)
            index = self.printer_combo.findData(name)
            if index >= 0:
                self.printer_combo.setCurrentIndex(index)
            index = self.paper_combo.findData(get_paper_mode(db))
            if index >= 0:
                self.paper_combo.setCurrentIndex(index)
            self.print_dialog_check.setChecked(get_show_dialog(db))
            index = self.a4_combo.findData(get_a4_printer(db))
            if index >= 0:
                self.a4_combo.setCurrentIndex(index)
        except Exception:
            pass

    def _empresa_actual(self) -> dict:
        """Datos de empresa en pantalla, para la muestra del formato."""
        return {
            "company_name": self.company_name_input.text().strip(),
            "company_id": self.company_id_input.text().strip(),
            "phone": self.phone_input.text().strip(),
            "address": self.address_input.text().strip(),
            "activity_code": self.activity_input.text().strip(),
            "email": self.email_input.text().strip(),
            "iban": self.iban_input.text().strip(),
            "sinpe": self.sinpe_input.text().strip(),
            "logo": self.logo_input.text().strip(),
        }

    def _crear_ticket_format_dialog(self):
        """Crea (sin abrir) el editor del formato con lo elegido en esta pestaña."""
        from modules.documentos.ticket import get_paper_mode
        from modules.settings.ticket_format_dialog import TicketFormatDialog

        db = self.services.get("db")
        modo = self.paper_combo.currentData() or (
            get_paper_mode(db) if db is not None else "")
        return TicketFormatDialog(
            self.services, company=self._empresa_actual(),
            printer_name=self.printer_combo.currentData() or "",
            paper_mode=modo, parent=self)

    def _open_ticket_format_dialog(self, _checked: bool = False) -> None:
        """Abre el editor visual del tiquete (ventana emergente)."""
        self._crear_ticket_format_dialog().exec()

    def _test_printer(self) -> None:
        """Abre la vista previa del ticket de prueba (imprimir o cerrar)."""
        from modules.documentos.ticket import (
            get_paper_mode,
            previsualizar_ticket,
            ticket_prueba_html,
        )
        printer_name = self.printer_combo.currentData() or ""
        db = self.services.get("db")
        modo = self.paper_combo.currentData() or (
            get_paper_mode(db) if db is not None else "")

        def _factory(font_pt, line_spacing, *_extra):
            nombre_papel = self.paper_combo.currentText()
            etiqueta = (f"Impresora: {printer_name or 'Predeterminada de Windows'}"
                        f" | Papel: {nombre_papel}")
            return ticket_prueba_html(etiqueta, font_pt=font_pt,
                                      line_spacing=line_spacing)

        from modules.documentos.ticket import get_ticket_settings
        ajustes = get_ticket_settings(db)
        html = _factory(ajustes.get("font_pt"), ajustes.get("line_spacing"))
        try:
            ok = previsualizar_ticket(
                html, printer_name, modo, parent=self, db=db,
                html_factory=_factory, ajustes=ajustes)
        except Exception as exc:
            QMessageBox.warning(self, "Impresora",
                                f"No se pudo abrir la vista previa:\n{exc}")
            return
        if not ok:
            QMessageBox.warning(
                self, "Impresora",
                "No se pudo preparar la impresora.\nVerifique que esté "
                "encendida, conectada y no sea un PDF/XPS.")

    def _test_a4(self) -> None:
        """Imprime una factura A4 de ejemplo en la impresora de hojas elegida."""
        db = self.services.get("db")
        try:
            from database.models import Sale, SaleItem
            from modules.documentos.pdf_factura import (
                factura_html,
                get_a4_printer,
                imprimir_factura,
            )
            from modules.documentos.xml_factura import cargar_empresa

            company = cargar_empresa(db) if db is not None else {}
            venta = Sale(
                invoice_number="V-EJEMPLO", client_name="Cliente de ejemplo",
                subtotal=13274.34, tax_amount=1725.66, total=15000.0,
                payment_method="efectivo", invoice_type="general",
                currency="CRC", exchange_rate=520.0, status="completada",
                hacienda_status="ACEPTADA", station="CAJA1",
                user_name="PRUEBA", created_at="2026-09-21 09:00:00",
                items=[SaleItem(product_id=1, product_name="Producto de ejemplo",
                                quantity=1, unit_price=13274.34,
                                tax_amount=1725.66, total=13274.34)],
            )
            html = factura_html(venta, company)
            destino = get_a4_printer(db) if db is not None else ""
            if imprimir_factura(html, destino):
                QMessageBox.information(
                    self, "Factura A4",
                    "Factura A4 de ejemplo enviada a la impresora.")
            else:
                QMessageBox.warning(
                    self, "Factura A4",
                    "No se imprimió: la impresora elegida no sirve para hojas "
                    "A4 (la térmica de 80 mm no imprime A4).\nElija una "
                    "impresora A4 en «Impresora para facturas A4».")
        except Exception as exc:
            QMessageBox.warning(self, "Factura A4",
                                f"No se pudo probar la factura A4:\n{exc}")

    # ---------- documentos ----------

    def _load_docs_path(self) -> None:
        try:
            from modules.documentos.paths import facturas_root
            self.docs_path_label.setText(str(facturas_root()))
        except Exception:
            self.docs_path_label.setText("No disponible")

    def _open_docs_folder(self) -> None:
        import subprocess
        from modules.documentos.paths import facturas_root
        carpeta = facturas_root()
        try:
            subprocess.Popen(f'explorer "{carpeta}"')
        except Exception as exc:
            QMessageBox.warning(self, "Documentos", f"No se pudo abrir la carpeta:\n{exc}")

    def _test_docs_folder(self) -> None:
        try:
            from modules.documentos.paths import facturas_root
            carpeta = facturas_root()
            prueba = carpeta / ".prueba_escritura"
            prueba.write_text("ok", encoding="utf-8")
            prueba.unlink(missing_ok=True)
            QMessageBox.information(
                self, "Documentos",
                f"La carpeta responde correctamente:\n{carpeta}")
        except OSError as exc:
            QMessageBox.warning(
                self, "Documentos",
                f"No se pudo escribir en la carpeta:\n{exc}\n\n"
                "Se usará la carpeta local de respaldo.")
        except Exception as exc:
            QMessageBox.warning(self, "Documentos", f"Error: {exc}")

    # ---------- actualizaciones ----------

    def _load_version(self) -> None:
        from config import Config
        self.version_label.setText(f"POS La Loma {Config.APP_VERSION}")

    def _check_updates(self) -> None:
        from network.updater import (UpdateError, consultar_actualizaciones,
                                     descargar_setup, hay_actualizacion,
                                     instalar_setup)
        from config import Config
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            info = consultar_actualizaciones()
            hay, version_nueva, setup = hay_actualizacion(info)
            if not hay:
                QMessageBox.information(
                    self, "Actualizaciones",
                    f"Ya tiene la versión más reciente ({Config.APP_VERSION}).")
                return
            respuesta = QMessageBox.question(
                self, "Actualización disponible",
                f"Hay una versión nueva ({version_nueva}).\n\n"
                "Se descargará del servidor y se instalará. La aplicación se "
                "cerrará para completar la actualización.\n\n¿Desea continuar?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if respuesta != QMessageBox.StandardButton.Yes:
                return
            from network.updater import carpeta_updates_local
            ruta = descargar_setup(setup, carpeta_updates_local())
            instalar_setup(ruta)
            QApplication.quit()
        except UpdateError as exc:
            QMessageBox.warning(self, "Actualizaciones", str(exc))
        except Exception as exc:
            QMessageBox.warning(self, "Actualizaciones", f"Error al actualizar:\n{exc}")
        finally:
            QApplication.restoreOverrideCursor()
