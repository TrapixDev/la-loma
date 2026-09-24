"""Visor de vista previa del ticket (estilo Chrome, con ajustes editables).

Muestra el ticket como una sola página blanca y permite ajustar en vivo el
tamaño de letra, los márgenes, el ancho y el papel; se puede imprimir, guardar
esos valores como predeterminados de la caja o copiar el diagnóstico de la
impresora.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPageSize, QPainter, QPixmap, QTextDocument
from PyQt6.QtPrintSupport import QPrinterInfo
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from modules.documentos.ticket import (
    DEFAULT_FONT_PT,
    DEFAULT_LINE_SPACING,
    PAPER_MODES,
    SCALE_FIT,
    SCALE_MODES,
    SCALE_REAL,
    _MARGIN_MM,
    _TICKET_WIDTH_MM,
    _es_impresora_prueba,
    _preparar_impresora,
    advertencia_papel,
    escala_necesaria,
    imprimir_ticket,
    save_ticket_settings,
    tamanos_soportados,
    ultima_salida_pdf,
)

_DPI = 150.0
_PX_POR_MM = _DPI / 25.4


def render_ticket(html: str, ancho_mm: float = _TICKET_WIDTH_MM,
                  margin_mm: float = _MARGIN_MM) -> QPixmap:
    """Renderiza el ticket completo como una sola página blanca."""
    ancho_mm = max(20.0, float(ancho_mm or _TICKET_WIDTH_MM))
    margin_mm = max(0.0, float(margin_mm if margin_mm is not None else _MARGIN_MM))
    margen_px = int(round(margin_mm * _PX_POR_MM))
    ancho_px = max(1, int(round(ancho_mm * _PX_POR_MM)))
    doc = QTextDocument()
    doc.setHtml(html)
    doc.setTextWidth(max(1, ancho_px - 2 * margen_px))
    alto_px = max(1, int(doc.size().height()) + 2 * margen_px)
    imagen = QImage(ancho_px, alto_px, QImage.Format.Format_RGB32)
    imagen.fill(0xFFFFFFFF)
    painter = QPainter(imagen)
    painter.translate(margen_px, margen_px)
    doc.drawContents(painter)
    painter.end()
    return QPixmap.fromImage(imagen)


class TicketPreviewDialog(QDialog):
    """Vista previa del ticket con panel de impresión y ajustes editables."""

    def __init__(self, html: str, printer_name: str = "",
                 modo_papel: str = "", parent=None, db=None,
                 html_factory=None, ajustes: dict | None = None):
        super().__init__(parent)
        self._db = db
        self._factory = html_factory
        self._ajustes = dict(ajustes or {})
        self._html = html
        self._font = float(self._ajustes.get("font_pt", DEFAULT_FONT_PT))
        self._spacing = float(self._ajustes.get("line_spacing",
                                                DEFAULT_LINE_SPACING))
        self._margins = float(self._ajustes.get("margin_mm", _MARGIN_MM))
        self._width = float(self._ajustes.get("width_mm", _TICKET_WIDTH_MM))
        self._scale_mode = self._ajustes.get("scale_mode", SCALE_FIT)
        self.setWindowTitle("Vista previa del ticket")
        self.setMinimumSize(980, 640)
        self._zoom = 1.0
        self._ajustar = True
        self._pagina = render_ticket(self._html, self._width, self._margins)
        self._setup_ui(printer_name, modo_papel)
        self._actualizar_aviso()

    # ---------- UI ----------

    def _setup_ui(self, printer_name: str, modo_papel: str) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        izquierda = QWidget()
        izquierda.setObjectName("previewFondo")
        izquierda_layout = QVBoxLayout(izquierda)
        izquierda_layout.setContentsMargins(10, 8, 10, 10)
        izquierda_layout.setSpacing(6)

        zoom_row = QHBoxLayout()
        zoom_row.setSpacing(6)
        self.zoom_label = QLabel("100%")
        self.zoom_label.setObjectName("previewZoom")
        boton_ajustar = QPushButton("Ajustar")
        boton_ajustar.setObjectName("secondaryButton")
        boton_ajustar.clicked.connect(self._ajustar_ancho)
        boton_menos = QPushButton("−")
        boton_menos.setObjectName("secondaryButton")
        boton_menos.setFixedWidth(38)
        boton_menos.clicked.connect(lambda: self._cambiar_zoom(-0.15))
        boton_mas = QPushButton("+")
        boton_mas.setObjectName("secondaryButton")
        boton_mas.setFixedWidth(38)
        boton_mas.clicked.connect(lambda: self._cambiar_zoom(0.15))
        zoom_row.addWidget(boton_ajustar)
        zoom_row.addWidget(boton_menos)
        zoom_row.addWidget(self.zoom_label)
        zoom_row.addWidget(boton_mas)
        zoom_row.addStretch(1)
        izquierda_layout.addLayout(zoom_row)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        contenedor = QWidget()
        contenedor_layout = QVBoxLayout(contenedor)
        contenedor_layout.setContentsMargins(0, 0, 0, 0)
        contenedor_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter
                                       | Qt.AlignmentFlag.AlignTop)
        self.hoja = QLabel()
        self.hoja.setObjectName("previewHoja")
        self.hoja.setAlignment(Qt.AlignmentFlag.AlignTop)
        contenedor_layout.addWidget(self.hoja)
        self.scroll.setWidget(contenedor)
        izquierda_layout.addWidget(self.scroll, 1)
        root.addWidget(izquierda, 1)

        panel = QWidget()
        panel.setObjectName("previewPanel")
        panel.setFixedWidth(268)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(16, 14, 16, 14)
        panel_layout.setSpacing(8)

        titulo = QLabel("Imprimir")
        titulo.setObjectName("previewTitulo")
        panel_layout.addWidget(titulo)

        panel_layout.addWidget(self._label("Destino:"))
        self.destino_combo = QComboBox()
        for impresora in QPrinterInfo.availablePrinters():
            self.destino_combo.addItem(impresora.printerName(),
                                       impresora.printerName())
        indice = self.destino_combo.findData(
            _nombre_real(printer_name))
        if indice < 0 and printer_name:
            indice = self.destino_combo.findData(printer_name)
        if indice >= 0:
            self.destino_combo.setCurrentIndex(indice)
        self.destino_combo.currentIndexChanged.connect(self._actualizar_aviso)
        panel_layout.addWidget(self.destino_combo)

        fila1 = QHBoxLayout()
        fila1.setSpacing(8)
        col_copias = QVBoxLayout()
        col_copias.setSpacing(2)
        col_copias.addWidget(self._label("Copias:"))
        self.copias_spin = QSpinBox()
        self.copias_spin.setRange(1, 10)
        self.copias_spin.setValue(1)
        self.copias_spin.wheelEvent = lambda event: event.ignore()
        col_copias.addWidget(self.copias_spin)
        fila1.addLayout(col_copias, 1)
        col_letra = QVBoxLayout()
        col_letra.setSpacing(2)
        col_letra.addWidget(self._label("Letra:"))
        self.font_spin = QDoubleSpinBox()
        self.font_spin.setRange(6.0, 20.0)
        self.font_spin.setSingleStep(0.5)
        self.font_spin.setDecimals(1)
        self.font_spin.setSuffix(" pt")
        self.font_spin.setValue(self._font)
        self.font_spin.wheelEvent = lambda event: event.ignore()
        self.font_spin.valueChanged.connect(self._aplicar_cambios)
        col_letra.addWidget(self.font_spin)
        fila1.addLayout(col_letra, 1)
        panel_layout.addLayout(fila1)

        fila2 = QHBoxLayout()
        fila2.setSpacing(8)
        col_margen = QVBoxLayout()
        col_margen.setSpacing(2)
        col_margen.addWidget(self._label("Márgenes:"))
        self.margin_spin = QDoubleSpinBox()
        self.margin_spin.setRange(0.0, 12.0)
        self.margin_spin.setSingleStep(0.5)
        self.margin_spin.setDecimals(1)
        self.margin_spin.setSuffix(" mm")
        self.margin_spin.setValue(self._margins)
        self.margin_spin.wheelEvent = lambda event: event.ignore()
        self.margin_spin.valueChanged.connect(self._aplicar_cambios)
        col_margen.addWidget(self.margin_spin)
        fila2.addLayout(col_margen, 1)
        col_ancho = QVBoxLayout()
        col_ancho.setSpacing(2)
        col_ancho.addWidget(self._label("Ancho:"))
        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(40.0, 112.0)
        self.width_spin.setSingleStep(2.0)
        self.width_spin.setDecimals(0)
        self.width_spin.setSuffix(" mm")
        self.width_spin.setValue(self._width)
        self.width_spin.wheelEvent = lambda event: event.ignore()
        self.width_spin.valueChanged.connect(self._aplicar_cambios)
        col_ancho.addWidget(self.width_spin)
        fila2.addLayout(col_ancho, 1)
        panel_layout.addLayout(fila2)

        fila3 = QHBoxLayout()
        fila3.setSpacing(8)
        col_inter = QVBoxLayout()
        col_inter.setSpacing(2)
        col_inter.addWidget(self._label("Interlineado:"))
        self.spacing_spin = QDoubleSpinBox()
        self.spacing_spin.setRange(1.0, 2.0)
        self.spacing_spin.setSingleStep(0.05)
        self.spacing_spin.setDecimals(2)
        self.spacing_spin.setValue(self._spacing)
        self.spacing_spin.wheelEvent = lambda event: event.ignore()
        self.spacing_spin.valueChanged.connect(self._aplicar_cambios)
        col_inter.addWidget(self.spacing_spin)
        fila3.addLayout(col_inter, 1)
        col_ajuste = QVBoxLayout()
        col_ajuste.setSpacing(2)
        col_ajuste.addWidget(self._label("Ajuste:"))
        self.scale_combo = QComboBox()
        for clave, etiqueta in SCALE_MODES.items():
            self.scale_combo.addItem(etiqueta, clave)
        indice = self.scale_combo.findData(self._scale_mode)
        if indice >= 0:
            self.scale_combo.setCurrentIndex(indice)
        self.scale_combo.currentIndexChanged.connect(self._aplicar_cambios)
        col_ajuste.addWidget(self.scale_combo)
        fila3.addLayout(col_ajuste, 1)
        panel_layout.addLayout(fila3)

        panel_layout.addWidget(self._label("Papel del ticket:"))
        self.papel_combo = QComboBox()
        for clave, etiqueta in PAPER_MODES.items():
            self.papel_combo.addItem(etiqueta, clave)
        indice = self.papel_combo.findData(modo_papel or "windows")
        if indice >= 0:
            self.papel_combo.setCurrentIndex(indice)
        self.papel_combo.currentIndexChanged.connect(self._actualizar_aviso)
        panel_layout.addWidget(self.papel_combo)

        self.papel_label = QLabel("")
        self.papel_label.setObjectName("previewEtiqueta")
        self.papel_label.setWordWrap(True)
        panel_layout.addWidget(self.papel_label)

        self.aviso_label = QLabel("")
        self.aviso_label.setObjectName("previewAviso")
        self.aviso_label.setWordWrap(True)
        self.aviso_label.setVisible(False)
        panel_layout.addWidget(self.aviso_label)

        panel_layout.addStretch(1)

        self.guardar_btn = QPushButton("Guardar como predeterminado")
        self.guardar_btn.setObjectName("secondaryButton")
        self.guardar_btn.setToolTip(
            "Guarda la letra, los márgenes, el ancho y el papel para las "
            "próximas impresiones de esta caja.")
        self.guardar_btn.setEnabled(self._db is not None)
        self.guardar_btn.clicked.connect(self._guardar_predeterminados)
        panel_layout.addWidget(self.guardar_btn)

        self.diagnostico_btn = QPushButton("Copiar diagnóstico de impresora")
        self.diagnostico_btn.setObjectName("secondaryButton")
        self.diagnostico_btn.clicked.connect(self._copiar_diagnostico)
        panel_layout.addWidget(self.diagnostico_btn)

        self.imprimir_btn = QPushButton("Imprimir")
        self.imprimir_btn.setObjectName("primaryButton")
        self.imprimir_btn.clicked.connect(self._imprimir)
        panel_layout.addWidget(self.imprimir_btn)

        cancelar_btn = QPushButton("Cancelar")
        cancelar_btn.setObjectName("secondaryButton")
        cancelar_btn.clicked.connect(self.reject)
        panel_layout.addWidget(cancelar_btn)

        root.addWidget(panel)
        self._escala()

    def _label(self, texto: str) -> QLabel:
        etiqueta = QLabel(texto)
        etiqueta.setObjectName("previewEtiqueta")
        return etiqueta

    # ---------- zoom ----------

    def _escala(self) -> None:
        ancho = max(60, int(self._pagina.width() * self._zoom))
        pixmap = self._pagina.scaledToWidth(
            ancho, Qt.TransformationMode.SmoothTransformation)
        self.hoja.setPixmap(pixmap)
        self.zoom_label.setText(f"{int(self._zoom * 100)}%")

    def _cambiar_zoom(self, delta: float) -> None:
        self._ajustar = False
        self._zoom = max(0.3, min(2.5, self._zoom + delta))
        self._escala()

    def _ajustar_ancho(self) -> None:
        self._ajustar = True
        self._escala()

    def resizeEvent(self, event) -> None:  # noqa: N802 - API de Qt
        super().resizeEvent(event)
        if self._ajustar:
            disponible = max(120, self.scroll.viewport().width() - 24)
            self._zoom = max(0.3, min(2.5, disponible / self._pagina.width()))
            self._escala()

    # ---------- ajustes ----------

    def _aplicar_cambios(self) -> None:
        """Reconstruye el ticket con la letra/interlineado y re-renderiza."""
        self._font = float(self.font_spin.value())
        self._spacing = float(self.spacing_spin.value())
        self._margins = float(self.margin_spin.value())
        self._width = float(self.width_spin.value())
        self._scale_mode = self.scale_combo.currentData() or SCALE_FIT
        if self._factory is not None:
            try:
                self._html = self._factory(self._font, self._spacing)
            except Exception:
                pass
        self._pagina = render_ticket(self._html, self._width, self._margins)
        self._ajustar = True
        self._ajustar_ancho()
        self._actualizar_aviso()

    def _guardar_predeterminados(self) -> None:
        if self._db is None:
            return
        try:
            save_ticket_settings(
                self._db, self._font, self._margins, self._width,
                self._spacing, self._scale_mode)
            self.aviso_label.setText(
                "Ajustes guardados como predeterminados de esta caja.")
            self.aviso_label.setVisible(True)
        except Exception as exc:
            QMessageBox.warning(self, "Impresión",
                                f"No se pudieron guardar los ajustes:\n{exc}")

    # ---------- impresión ----------

    def _actualizar_aviso(self) -> None:
        destino = self.destino_combo.currentData() or ""
        modo = self.papel_combo.currentData() or ""
        printer = _preparar_impresora(destino, modo, self._html,
                                      width_mm=self._width,
                                      margin_mm=self._margins)
        if printer is None:
            self.imprimir_btn.setEnabled(False)
            self.papel_label.setText("")
            self.aviso_label.setText(
                "No hay una impresora válida seleccionada. Puede ver el "
                "ticket, pero no imprimirlo.")
            self.aviso_label.setVisible(True)
            return
        self.imprimir_btn.setEnabled(True)
        pagina = printer.pageLayout().pageSize()
        mm = pagina.size(QPageSize.Unit.Millimeter)
        escala = escala_necesaria(printer, self._html)
        detalle = f"Papel: {pagina.name()} ({mm.width():.0f}×{mm.height():.0f} mm)"
        if escala < 1.0:
            if self._scale_mode == SCALE_REAL:
                detalle += " · tamaño real (puede cortarse)"
            else:
                detalle += f" · se reduce al {escala * 100:.0f}%"
        if _es_impresora_prueba(destino):
            detalle += " · se guarda un PDF de prueba (Documentos\\PosLaLoma\\pruebas)"
        self.papel_label.setText(detalle)
        aviso = advertencia_papel(printer, self._html)
        if aviso and self._scale_mode == SCALE_REAL:
            aviso = ("El ticket es más largo que el papel y está en «Tamaño "
                     "real»: puede cortarse. Elija «Ajustar al papel» o un "
                     "papel más alto.")
        self.aviso_label.setText(aviso)
        self.aviso_label.setVisible(bool(aviso))

    def _copiar_diagnostico(self) -> None:
        """Copia al portapapeles los datos del driver (para soporte)."""
        from PyQt6.QtWidgets import QApplication

        destino = self.destino_combo.currentData() or ""
        lineas = [
            f"Impresora: {destino or '(predeterminada)'}",
            f"Ajustes: letra {self._font:.1f}pt · márgenes {self._margins:.1f}mm "
            f"· ancho {self._width:.0f}mm · interlineado {self._spacing:.2f} "
            f"· ajuste {self._scale_mode}",
        ]
        printer = _preparar_impresora(destino, self.papel_combo.currentData() or "",
                                      self._html, width_mm=self._width,
                                      margin_mm=self._margins)
        if printer is not None:
            pagina = printer.pageLayout().pageSize()
            mm = pagina.size(QPageSize.Unit.Millimeter)
            escala = escala_necesaria(printer, self._html)
            lineas.append(f"Papel usado: {pagina.name()} "
                          f"({mm.width():.1f} x {mm.height():.1f} mm)")
            lineas.append(f"Alto del contenido: {escala * 100:.0f}% de la página")
        tamanos = tamanos_soportados(destino)
        lineas.append(f"Tamaños soportados ({len(tamanos)}):")
        for nombre, ancho, alto in tamanos[:40]:
            lineas.append(f"  - {nombre} · {ancho:.1f} x {alto:.1f} mm")
        texto = "\n".join(lineas)
        try:
            QApplication.clipboard().setText(texto)
            self.aviso_label.setText(
                "Diagnóstico de impresora copiado al portapapeles.")
            self.aviso_label.setVisible(True)
        except Exception:
            self.aviso_label.setText("No se pudo copiar el diagnóstico.")
            self.aviso_label.setVisible(True)

    def _imprimir(self) -> None:
        destino = self.destino_combo.currentData() or ""
        modo = self.papel_combo.currentData() or ""
        copias = int(self.copias_spin.value())
        try:
            ok = imprimir_ticket(self._html, destino, modo, copias,
                                 width_mm=self._width, margin_mm=self._margins,
                                 reducir=self._scale_mode != SCALE_REAL)
        except Exception as exc:
            QMessageBox.warning(self, "Impresión",
                                f"No se pudo imprimir:\n{exc}")
            return
        if not ok:
            QMessageBox.warning(
                self, "Impresión",
                "No se pudo enviar a la impresora.\nVerifique que esté "
                "encendida, conectada y no sea un PDF/XPS.")
            return
        # Impresora virtual/prueba: se generó un PDF; se muestra para revisarlo.
        salida = ultima_salida_pdf()
        if salida:
            try:
                from PyQt6.QtCore import QUrl
                from PyQt6.QtGui import QDesktopServices

                QDesktopServices.openUrl(QUrl.fromLocalFile(salida))
            except Exception:
                pass
            QMessageBox.information(
                self, "Impresión de prueba",
                f"El ticket se guardó como PDF de prueba:\n{salida}")
        self.accept()


def _nombre_real(printer_name: str) -> str:
    """Nombre de Windows que corresponde al guardado (o el mismo)."""
    try:
        from modules.documentos.ticket import resolver_impresora
        return resolver_impresora(printer_name)
    except Exception:
        return printer_name
