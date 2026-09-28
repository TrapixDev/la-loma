"""Editor visual del formato del tiquete térmico (ventana emergente).

Antes vivía en la pestaña "Formato del ticket" de Configuración; ahora se
abre desde "Impresora y docs" con el botón "Formato del ticket…". Mantiene
los mismos controles: bloques visibles, textos y logo, tamaño y espaciado,
con vista previa en vivo de 80 mm sobre una venta ficticia.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from modules.documentos.ticket import (
    DEFAULT_FONT_PT,
    DEFAULT_LINE_SPACING,
    SCALE_FIT,
    SCALE_MODES,
    TICKET_FORMAT_DEFAULTS,
    _MARGIN_MM,
    _TICKET_WIDTH_MM,
    get_paper_mode,
    get_ticket_format,
    get_ticket_settings,
    normalizar_formato_ticket,
    previsualizar_ticket,
    save_ticket_format,
    save_ticket_settings,
    ticket_html,
)
from utils.helpers import NoWheelComboBox, NoWheelIntSpinBox, NoWheelSpinBox


class TicketFormatDialog(QDialog):
    """Diseño del tiquete de 80 mm con vista previa en vivo."""

    def __init__(self, services: dict | None = None,
                 company: dict | None = None, printer_name: str = "",
                 paper_mode: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.services = services or {}
        self._company = dict(company or {})
        self._printer_name = printer_name
        self._paper_mode = paper_mode
        self.memory_ticket_format: dict = {}
        self.memory_ticket_print_settings: dict = {}
        self._loading = False
        self.setWindowTitle("Formato del ticket")
        self.setMinimumSize(1000, 640)
        self.resize(1120, 720)
        self._setup_ui()
        self._load_values()

    # ---------- helpers ----------

    def _db(self):
        return self.services.get("db")

    def _label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("formLabel")
        return label

    # ---------- UI ----------

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(10)

        hint = QLabel(
            "Diseñá el tiquete de 80 mm y revisá cada cambio en la vista previa. "
            "La muestra usa datos ficticios; los datos reales se toman de Empresa.")
        hint.setObjectName("settingsHint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        contenido = QHBoxLayout()
        contenido.setSpacing(12)

        format_controls = QWidget()
        format_controls_layout = QVBoxLayout(format_controls)
        format_controls_layout.setContentsMargins(0, 0, 0, 0)
        format_controls_layout.setSpacing(10)
        self.ticket_format_checks: dict[str, QCheckBox] = {}

        def _format_check(key: str, text: str) -> QCheckBox:
            check = QCheckBox(text)
            check.stateChanged.connect(
                lambda _state: self._refresh_ticket_preview())
            self.ticket_format_checks[key] = check
            return check

        company_format_group = QGroupBox("Encabezado de la empresa")
        company_format_group.setObjectName("settingsGroup")
        company_format_grid = QGridLayout(company_format_group)
        company_format_grid.setContentsMargins(14, 12, 14, 12)
        company_format_grid.setHorizontalSpacing(16)
        company_format_grid.setVerticalSpacing(8)
        company_format_options = (
            ("show_logo", "Logo"),
            ("show_company_name", "Nombre de la empresa"),
            ("show_company_id", "Cédula jurídica"),
            ("show_address", "Dirección"),
            ("show_phone", "Teléfono"),
            ("show_email", "Correo electrónico"),
            ("show_activity", "Actividad económica"),
        )
        for index, (key, text) in enumerate(company_format_options):
            company_format_grid.addWidget(
                _format_check(key, text), index // 2, index % 2)
        format_controls_layout.addWidget(company_format_group)

        sale_format_group = QGroupBox("Información del tiquete")
        sale_format_group.setObjectName("settingsGroup")
        sale_format_grid = QGridLayout(sale_format_group)
        sale_format_grid.setContentsMargins(14, 12, 14, 12)
        sale_format_grid.setHorizontalSpacing(16)
        sale_format_grid.setVerticalSpacing(8)
        sale_format_options = (
            ("show_customer", "Cliente"),
            ("show_hacienda_key", "Clave de Hacienda"),
            ("show_payments", "Detalle del pago"),
            ("show_amount_words", "Monto en letras"),
            ("show_transfer_details", "IBAN / SINPE"),
            ("show_equivalent_crc", "Equivalente en colones"),
            ("show_status", "Estado del comprobante"),
            ("show_thank_you", "Agradecimiento"),
        )
        for index, (key, text) in enumerate(sale_format_options):
            sale_format_grid.addWidget(
                _format_check(key, text), index // 2, index % 2)
        self.ticket_format_checks["show_equivalent_crc"].setToolTip(
            "Solo se muestra en ventas en USD. También respeta "
            "mostrar_equivalente_crc en config.ini.")
        format_controls_layout.addWidget(sale_format_group)

        text_format_group = QGroupBox("Textos y logo")
        text_format_group.setObjectName("settingsGroup")
        text_format_form = QFormLayout(text_format_group)
        text_format_form.setContentsMargins(14, 12, 14, 12)
        text_format_form.setSpacing(8)
        self.ticket_logo_width_spin = NoWheelIntSpinBox()
        self.ticket_logo_width_spin.setRange(48, 240)
        self.ticket_logo_width_spin.setSuffix(" px")
        self.ticket_logo_width_spin.valueChanged.connect(
            lambda _value: self._refresh_ticket_preview())
        self.ticket_thank_you_input = QLineEdit()
        self.ticket_thank_you_input.setMaxLength(100)
        self.ticket_thank_you_input.setPlaceholderText(
            "GRACIAS POR SU PREFERENCIA")
        self.ticket_footer_input = QLineEdit()
        self.ticket_footer_input.setMaxLength(160)
        self.ticket_footer_input.setPlaceholderText(
            "Opcional: mensaje adicional al pie")
        self.ticket_thank_you_input.textChanged.connect(
            lambda _text: self._refresh_ticket_preview())
        self.ticket_footer_input.textChanged.connect(
            lambda _text: self._refresh_ticket_preview())
        self.ticket_format_checks["show_logo"].toggled.connect(
            self.ticket_logo_width_spin.setEnabled)
        self.ticket_format_checks["show_thank_you"].toggled.connect(
            self.ticket_thank_you_input.setEnabled)
        text_format_form.addRow(self._label("Ancho del logo:"),
                                self.ticket_logo_width_spin)
        text_format_form.addRow(self._label("Agradecimiento:"),
                                self.ticket_thank_you_input)
        text_format_form.addRow(self._label("Texto adicional al pie:"),
                                self.ticket_footer_input)
        format_controls_layout.addWidget(text_format_group)

        print_format_group = QGroupBox("Tamaño y espaciado")
        print_format_group.setObjectName("settingsGroup")
        print_format_form = QFormLayout(print_format_group)
        print_format_form.setContentsMargins(14, 12, 14, 12)
        print_format_form.setSpacing(8)
        self.ticket_font_spin = NoWheelSpinBox()
        self.ticket_font_spin.setRange(6.0, 20.0)
        self.ticket_font_spin.setSingleStep(0.5)
        self.ticket_font_spin.setDecimals(1)
        self.ticket_font_spin.setSuffix(" pt")
        self.ticket_line_spacing_spin = NoWheelSpinBox()
        self.ticket_line_spacing_spin.setRange(1.0, 2.0)
        self.ticket_line_spacing_spin.setSingleStep(0.05)
        self.ticket_line_spacing_spin.setDecimals(2)
        self.ticket_margin_spin = NoWheelSpinBox()
        self.ticket_margin_spin.setRange(0.0, 12.0)
        self.ticket_margin_spin.setSingleStep(0.5)
        self.ticket_margin_spin.setDecimals(1)
        self.ticket_margin_spin.setSuffix(" mm")
        self.ticket_width_spin = NoWheelSpinBox()
        self.ticket_width_spin.setRange(40.0, 112.0)
        self.ticket_width_spin.setSingleStep(2.0)
        self.ticket_width_spin.setDecimals(0)
        self.ticket_width_spin.setSuffix(" mm")
        self.ticket_scale_combo = NoWheelComboBox()
        for key, text in SCALE_MODES.items():
            self.ticket_scale_combo.addItem(text, key)
        for spin in (self.ticket_font_spin, self.ticket_line_spacing_spin,
                     self.ticket_margin_spin, self.ticket_width_spin):
            spin.valueChanged.connect(
                lambda _value: self._refresh_ticket_preview())
        self.ticket_scale_combo.currentIndexChanged.connect(
            lambda _index: self._refresh_ticket_preview())
        print_format_form.addRow(self._label("Tamaño de letra:"),
                                 self.ticket_font_spin)
        print_format_form.addRow(self._label("Interlineado:"),
                                 self.ticket_line_spacing_spin)
        print_format_form.addRow(self._label("Márgenes:"),
                                 self.ticket_margin_spin)
        print_format_form.addRow(self._label("Ancho de impresión:"),
                                 self.ticket_width_spin)
        print_format_form.addRow(self._label("Ajuste al papel:"),
                                 self.ticket_scale_combo)
        format_controls_layout.addWidget(print_format_group)

        format_controls_layout.addStretch(1)

        controls_scroll = QScrollArea()
        controls_scroll.setWidgetResizable(True)
        controls_scroll.setFrameShape(QFrame.Shape.NoFrame)
        controls_scroll.setWidget(format_controls)
        contenido.addWidget(controls_scroll, 3)

        preview_group = QGroupBox("Vista previa · tiquete de 80 mm")
        preview_group.setObjectName("settingsGroup")
        preview_group.setMinimumWidth(300)
        preview_layout = QVBoxLayout(preview_group)
        preview_layout.setContentsMargins(12, 12, 12, 12)
        preview_layout.setSpacing(8)
        preview_hint = QLabel(
            "Se actualiza al editar. La muestra usa productos de ejemplo.")
        preview_hint.setObjectName("settingsHint")
        preview_hint.setWordWrap(True)
        preview_layout.addWidget(preview_hint)
        self.ticket_preview_scroll = QScrollArea()
        self.ticket_preview_scroll.setWidgetResizable(False)
        self.ticket_preview_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.ticket_preview_scroll.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.ticket_preview_label = QLabel()
        self.ticket_preview_label.setObjectName("ticketFormatPreview")
        self.ticket_preview_label.setAlignment(Qt.AlignmentFlag.AlignHCenter
                                               | Qt.AlignmentFlag.AlignTop)
        self.ticket_preview_scroll.setWidget(self.ticket_preview_label)
        preview_layout.addWidget(self.ticket_preview_scroll, 1)
        preview_button = QPushButton("Abrir visor / imprimir prueba")
        preview_button.setObjectName("secondaryButton")
        preview_button.clicked.connect(self._open_print_preview)
        preview_layout.addWidget(preview_button)
        contenido.addWidget(preview_group, 2)

        root.addLayout(contenido, 1)

        pie = QHBoxLayout()
        pie.setSpacing(8)
        self.ticket_format_save_button = QPushButton("Guardar formato")
        self.ticket_format_save_button.setObjectName("primaryButton")
        self.ticket_format_save_button.clicked.connect(
            self._save_ticket_editor)
        ticket_format_reset_button = QPushButton("Restablecer formato")
        ticket_format_reset_button.setObjectName("secondaryButton")
        ticket_format_reset_button.clicked.connect(self._reset_ticket_format)
        self.ticket_format_status = QLabel("")
        self.ticket_format_status.setObjectName("settingsHint")
        self.ticket_format_status.setWordWrap(True)
        cerrar_button = QPushButton("Cerrar")
        cerrar_button.setObjectName("secondaryButton")
        cerrar_button.clicked.connect(self.reject)
        pie.addWidget(self.ticket_format_save_button)
        pie.addWidget(ticket_format_reset_button)
        pie.addWidget(self.ticket_format_status, 1)
        pie.addWidget(cerrar_button)
        root.addLayout(pie)

    # ---------- datos ----------

    def _ticket_format_values(self) -> dict:
        values = {
            key: check.isChecked()
            for key, check in self.ticket_format_checks.items()
        }
        values.update({
            "logo_width_px": self.ticket_logo_width_spin.value(),
            "thank_you_text": self.ticket_thank_you_input.text(),
            "footer_text": self.ticket_footer_input.text(),
        })
        return normalizar_formato_ticket(values)

    def _ticket_print_settings(self) -> dict:
        return {
            "font_pt": self.ticket_font_spin.value(),
            "line_spacing": self.ticket_line_spacing_spin.value(),
            "margin_mm": self.ticket_margin_spin.value(),
            "width_mm": self.ticket_width_spin.value(),
            "scale_mode": self.ticket_scale_combo.currentData() or SCALE_FIT,
        }

    def _apply_ticket_print_settings(self, settings: dict) -> None:
        self.ticket_font_spin.setValue(float(settings.get("font_pt", 12.0)))
        self.ticket_line_spacing_spin.setValue(
            float(settings.get("line_spacing", 1.35)))
        self.ticket_margin_spin.setValue(float(settings.get("margin_mm", 3.0)))
        self.ticket_width_spin.setValue(float(settings.get("width_mm", 80.0)))
        scale_index = self.ticket_scale_combo.findData(
            settings.get("scale_mode", SCALE_FIT))
        if scale_index >= 0:
            self.ticket_scale_combo.setCurrentIndex(scale_index)

    def _load_values(self) -> None:
        self._loading = True
        try:
            db = self._db()
            if db is None:
                formato = self.memory_ticket_format or TICKET_FORMAT_DEFAULTS
                settings = self.memory_ticket_print_settings or get_ticket_settings(None)
            else:
                formato = get_ticket_format(db)
                settings = get_ticket_settings(db)
            for key, check in self.ticket_format_checks.items():
                check.setChecked(bool(formato.get(key, TICKET_FORMAT_DEFAULTS[key])))
            self.ticket_logo_width_spin.setValue(
                int(formato.get("logo_width_px", 128)))
            self.ticket_thank_you_input.setText(
                formato.get("thank_you_text", ""))
            self.ticket_footer_input.setText(formato.get("footer_text", ""))
            self._apply_ticket_print_settings(settings)
            self.ticket_logo_width_spin.setEnabled(
                formato.get("show_logo", True))
            self.ticket_thank_you_input.setEnabled(
                formato.get("show_thank_you", True))
            self.ticket_format_status.setText("")
        except Exception:
            pass
        finally:
            self._loading = False
        self._refresh_ticket_preview()

    # ---------- vista previa ----------

    @staticmethod
    def _ticket_preview_sale():
        from database.models import Sale, SaleItem

        return Sale(
            id=0,
            invoice_number="V-EJEMPLO",
            client_name="Cliente de ejemplo",
            subtotal=100000.0,
            tax_amount=13000.0,
            total=113000.0,
            payment_method="tarjeta",
            cash_received=113000.0,
            invoice_type="general",
            currency="CRC",
            exchange_rate=520.0,
            status="completada",
            hacienda_key="50625092500310112345600100001010000000001111111",
            hacienda_status="ACEPTADA",
            electronic_invoice=True,
            station="CAJA1",
            user_name="CAJERO",
            created_at="2026-09-25 10:30:00",
            items=[
                SaleItem(product_id=1, product_name="Silla de madera",
                         quantity=1, unit_price=25000.0, total=25000.0),
                SaleItem(product_id=2,
                         product_name="Mesa de comedor de madera sólida",
                         quantity=1, unit_price=75000.0, total=75000.0),
            ],
        )

    def _refresh_ticket_preview(self) -> None:
        if self._loading or not hasattr(self, "ticket_preview_label"):
            return
        try:
            from modules.documentos.ticket import ticket_html
            from ui.ticket_preview import render_ticket

            settings = self._ticket_print_settings()
            html = ticket_html(
                self._ticket_preview_sale(), self._company,
                font_pt=settings["font_pt"],
                line_spacing=settings["line_spacing"],
                formato=self._ticket_format_values())
            self.ticket_preview_html = html
            pixmap = render_ticket(
                html, settings["width_mm"], settings["margin_mm"])
            self._ticket_preview_pixmap = pixmap
            viewport_width = self.ticket_preview_scroll.viewport().width()
            preview_width = max(240, min(340, viewport_width - 12))
            scaled = pixmap.scaledToWidth(
                preview_width, Qt.TransformationMode.SmoothTransformation)
            self.ticket_preview_label.setPixmap(scaled)
            self.ticket_preview_label.setFixedSize(scaled.size())
        except Exception as exc:
            self.ticket_preview_html = ""
            self.ticket_preview_label.clear()
            self.ticket_preview_label.setText(
                f"No se pudo renderizar la muestra: {exc}")

    # ---------- guardar / restablecer ----------

    def _persist_ticket_editor(self) -> bool:
        formato = self._ticket_format_values()
        settings = self._ticket_print_settings()
        db = self._db()
        if db is None:
            self.memory_ticket_format = formato
            self.memory_ticket_print_settings = settings
        else:
            try:
                save_ticket_format(db, formato)
                save_ticket_settings(
                    db, settings["font_pt"], settings["margin_mm"],
                    settings["width_mm"], settings["line_spacing"],
                    settings["scale_mode"])
            except Exception as exc:
                self.ticket_format_status.setText(
                    f"No se pudo guardar el formato: {exc}")
                return False
        self.ticket_format_status.setText(
            "Formato del tiquete guardado para esta base de datos.")
        return True

    def _save_ticket_editor(self, _checked: bool = False) -> None:
        if self._persist_ticket_editor():
            QMessageBox.information(
                self, "Formato del ticket",
                "El formato del tiquete quedó guardado.")

    def _reset_ticket_format(self, _checked: bool = False) -> None:
        self._loading = True
        try:
            for key, check in self.ticket_format_checks.items():
                check.setChecked(TICKET_FORMAT_DEFAULTS[key])
            self.ticket_logo_width_spin.setValue(
                TICKET_FORMAT_DEFAULTS["logo_width_px"])
            self.ticket_thank_you_input.setText(
                TICKET_FORMAT_DEFAULTS["thank_you_text"])
            self.ticket_footer_input.setText(
                TICKET_FORMAT_DEFAULTS["footer_text"])
            self._apply_ticket_print_settings({
                "font_pt": DEFAULT_FONT_PT,
                "line_spacing": DEFAULT_LINE_SPACING,
                "margin_mm": _MARGIN_MM,
                "width_mm": _TICKET_WIDTH_MM,
                "scale_mode": SCALE_FIT,
            })
            self.ticket_logo_width_spin.setEnabled(True)
            self.ticket_thank_you_input.setEnabled(True)
            self.ticket_format_status.setText(
                "Valores iniciales cargados. Pulsá Guardar formato para aplicarlos.")
        finally:
            self._loading = False
        self._refresh_ticket_preview()

    # ---------- impresión ----------

    def _open_print_preview(self, _checked: bool = False) -> None:
        sale = self._ticket_preview_sale()
        company = dict(self._company)
        formato = self._ticket_format_values()
        ajustes = self._ticket_print_settings()

        def html_factory(font_pt, line_spacing, *_extra):
            return ticket_html(
                sale, company, font_pt=font_pt,
                line_spacing=line_spacing, formato=formato)

        html = html_factory(ajustes["font_pt"], ajustes["line_spacing"])
        db = self._db()
        modo = self._paper_mode or (
            get_paper_mode(db) if db is not None else "")
        try:
            ok = previsualizar_ticket(
                html, self._printer_name, modo,
                parent=self, db=db, html_factory=html_factory,
                ajustes=ajustes)
        except Exception as exc:
            QMessageBox.warning(
                self, "Vista previa del ticket",
                f"No se pudo abrir el visor:\n{exc}")
            return
        if not ok:
            QMessageBox.warning(
                self, "Vista previa del ticket",
                "No se pudo preparar la impresora. Revisá la pestaña "
                "Impresora y docs.")
            return

        if db is not None:
            self._loading = True
            try:
                self._apply_ticket_print_settings(get_ticket_settings(db))
            finally:
                self._loading = False
            self._refresh_ticket_preview()
