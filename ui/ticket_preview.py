"""Visor de vista previa del ticket (estilo Chrome: hoja + panel de impresión).

Muestra el ticket completo como una sola página blanca (igual a lo que se
imprime) y un panel simple con destino, copias, papel y los botones
Imprimir / Cancelar.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPageSize, QPainter, QPixmap, QTextDocument
from PyQt6.QtPrintSupport import QPrinterInfo
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
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
    PAPER_MODES,
    _MARGIN_MM,
    _TICKET_WIDTH_MM,
    _preparar_impresora,
    advertencia_papel,
    escala_necesaria,
    imprimir_ticket,
    tamanos_soportados,
)

_DPI = 150.0
_PX_POR_MM = _DPI / 25.4


def render_ticket(html: str, ancho_mm: float = _TICKET_WIDTH_MM) -> QPixmap:
    """Renderiza el ticket completo como una sola página blanca."""
    margen_px = int(round(_MARGIN_MM * _PX_POR_MM))
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
    """Vista previa del ticket con panel de impresión simple."""

    def __init__(self, html: str, printer_name: str = "",
                 modo_papel: str = "", parent=None):
        super().__init__(parent)
        self._html = html
        self.setWindowTitle("Vista previa del ticket")
        self.setMinimumSize(900, 620)
        self._zoom = 1.0
        self._ajustar = True
        self._pagina = render_ticket(html)
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
        panel.setFixedWidth(252)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(16, 16, 16, 16)
        panel_layout.setSpacing(10)

        titulo = QLabel("Imprimir")
        titulo.setObjectName("previewTitulo")
        panel_layout.addWidget(titulo)

        panel_layout.addWidget(self._label("Destino:"))
        self.destino_combo = QComboBox()
        for impresora in QPrinterInfo.availablePrinters():
            self.destino_combo.addItem(impresora.printerName(),
                                       impresora.printerName())
        indice = self.destino_combo.findData(printer_name)
        if indice >= 0:
            self.destino_combo.setCurrentIndex(indice)
        self.destino_combo.currentIndexChanged.connect(self._actualizar_aviso)
        panel_layout.addWidget(self.destino_combo)

        panel_layout.addWidget(self._label("Copias:"))
        self.copias_spin = QSpinBox()
        self.copias_spin.setRange(1, 10)
        self.copias_spin.setValue(1)
        self.copias_spin.wheelEvent = lambda event: event.ignore()
        panel_layout.addWidget(self.copias_spin)

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
        pixmap = self._pagina.scaledToWidth(ancho, Qt.TransformationMode.SmoothTransformation)
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

    # ---------- impresión ----------

    def _actualizar_aviso(self) -> None:
        destino = self.destino_combo.currentData() or ""
        modo = self.papel_combo.currentData() or ""
        printer = _preparar_impresora(destino, modo, self._html)
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
            detalle += f" · se reduce al {escala * 100:.0f}% para que quepa"
        self.papel_label.setText(detalle)
        aviso = advertencia_papel(printer, self._html)
        self.aviso_label.setText(aviso)
        self.aviso_label.setVisible(bool(aviso))

    def _copiar_diagnostico(self) -> None:
        """Copia al portapapeles los datos del driver (para soporte)."""
        from PyQt6.QtWidgets import QApplication

        destino = self.destino_combo.currentData() or ""
        lineas = [f"Impresora: {destino or '(predeterminada)'}"]
        printer = _preparar_impresora(destino, self.papel_combo.currentData() or "",
                                      self._html)
        if printer is not None:
            pagina = printer.pageLayout().pageSize()
            mm = pagina.size(QPageSize.Unit.Millimeter)
            lineas.append(f"Papel usado: {pagina.name()} "
                          f"({mm.width():.1f} x {mm.height():.1f} mm)")
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
            ok = imprimir_ticket(self._html, destino, modo, copias)
        except Exception as exc:
            QMessageBox.warning(self, "Impresión",
                                f"No se pudo imprimir:\n{exc}")
            return
        if ok:
            self.accept()
        else:
            QMessageBox.warning(
                self, "Impresión",
                "No se pudo enviar a la impresora.\nVerifique que esté "
                "encendida, conectada y no sea un PDF/XPS.")
