"""Widget de configuración de empresa y Hacienda (tarjetas agrupadas)."""

from PyQt6.QtCore import Qt
from PyQt6.QtPrintSupport import QPrinterInfo
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFormLayout,
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

from utils.helpers import NoWheelComboBox

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

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(4, 8, 4, 8)
        layout.setSpacing(16)
        content.setMaximumWidth(760)

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

        company_form.addRow(self._label("Nombre de la empresa:"), self.company_name_input)
        company_form.addRow(self._label("Cédula jurídica:"), self.company_id_input)
        company_form.addRow(self._label("Teléfono:"), self.phone_input)
        company_form.addRow(self._label("Dirección:"), self.address_input)
        company_form.addRow(self._label("Actividad económica:"), self.activity_input)
        layout.addWidget(company_group)

        # ---------- Tarjeta 2: Hacienda ----------
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
        layout.addWidget(hacienda_group)

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
        layout.addWidget(currency_group)

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

        test_printer_button = QPushButton("Probar impresión")
        test_printer_button.setObjectName("primaryButton")
        test_printer_button.clicked.connect(self._test_printer)

        printer_hint = QLabel("Se usa al imprimir tickets de venta (térmica 80mm)")
        printer_hint.setObjectName("settingsHint")
        printer_form.addRow(self._label("Impresora de tickets:"), self.printer_combo)
        printer_form.addRow("", test_printer_button)
        printer_form.addRow("", printer_hint)
        layout.addWidget(printer_group)

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
        layout.addWidget(docs_group)

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
        layout.addWidget(update_group)

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
        layout.addLayout(buttons)

        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

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
        db = self.services.get("db")
        if db is not None:
            try:
                rows = db.execute_query("SELECT * FROM hacienda_config WHERE id = 1") or []
                if rows:
                    row = {str(key): value for key, value in rows[0].items()}
                    config = {key: row.get(column, "") for key, column in COLUMN_MAP.items()}
                    self._apply_config(config)
                    return
            except Exception:
                pass
        if self.memory_config:
            self._apply_config(self.memory_config)

    def _save(self) -> None:
        values = self._config_values()
        db = self.services.get("db")
        if db is not None:
            columns = [COLUMN_MAP[key] for key in values]
            placeholders = ", ".join("?" for _ in columns)
            sql = (
                f"INSERT OR REPLACE INTO hacienda_config (id, {', '.join(columns)}) "
                f"VALUES (1, {placeholders})"
            )
            try:
                db.execute_insert(sql, tuple(values[key] for key in values))
                self._save_printer()
                QMessageBox.information(self, "Configuración", "Configuración guardada correctamente.")
                return
            except Exception as exc:
                try:
                    for key, value in values.items():
                        db.execute_insert(
                            "INSERT OR REPLACE INTO hacienda_config (key, value) VALUES (?, ?)",
                            (key, str(value)),
                        )
                    self._save_printer()
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
        """Guarda la impresora de tickets seleccionada en app_config."""
        db = self.services.get("db")
        if db is None:
            return
        try:
            from modules.documentos.ticket import save_printer_name
            save_printer_name(db, self.printer_combo.currentData() or "")
        except Exception:
            pass

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
        """Carga la impresora de tickets guardada en la base de datos."""
        db = self.services.get("db")
        if db is None:
            return
        try:
            from modules.documentos.ticket import get_printer_name
            name = get_printer_name(db)
            index = self.printer_combo.findData(name)
            if index >= 0:
                self.printer_combo.setCurrentIndex(index)
        except Exception:
            pass

    def _test_printer(self) -> None:
        """Imprime un ticket de prueba en la impresora seleccionada."""
        from modules.documentos.ticket import imprimir_prueba
        printer_name = self.printer_combo.currentData() or ""
        if imprimir_prueba(printer_name):
            QMessageBox.information(
                self, "Impresora",
                "Ticket de prueba enviado a la impresora.")
        else:
            QMessageBox.warning(
                self, "Impresora",
                "No se pudo imprimir.\nVerifique que la impresora esté encendida, "
                "conectada y no sea un PDF/XPS.")

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
