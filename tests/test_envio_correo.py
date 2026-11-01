"""Envío automático de la factura electrónica por correo (SMTP simulado)."""

import os
import smtplib
import ssl
import sys
from pathlib import Path
from types import SimpleNamespace

PROJECT_DIR = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, PROJECT_DIR)
os.chdir(PROJECT_DIR)

import pytest

from database.db_manager import DatabaseManager
from modules.documentos import email_service as es

COMPANY = {"company_name": "Muebleria La Loma", "phone": "2222-0000",
           "email": "info@laloma.cr"}


class _FakeSMTPBase:
    """Registra lo que haría un servidor SMTP real."""

    instancias: list = []
    error_login: Exception | None = None
    error_envio: Exception | None = None

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port = host, port
        self.timeout, self.context = timeout, context
        self.acciones: list = []
        self.mensajes: list = []
        type(self).instancias.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def ehlo(self):
        self.acciones.append("ehlo")

    def starttls(self, context=None):
        self.acciones.append("starttls")
        self.context_tls = context

    def login(self, usuario, password):
        if type(self).error_login:
            raise type(self).error_login
        self.acciones.append(("login", usuario, password))

    def send_message(self, msg):
        if type(self).error_envio:
            raise type(self).error_envio
        self.mensajes.append(msg)


class FakeSMTP(_FakeSMTPBase):
    instancias: list = []
    error_login = None
    error_envio = None


class FakeSMTPSSL(_FakeSMTPBase):
    instancias: list = []
    error_login = None
    error_envio = None


@pytest.fixture(autouse=True)
def smtp_falso(monkeypatch, tmp_path):
    for clase in (FakeSMTP, FakeSMTPSSL):
        clase.instancias = []
        clase.error_login = None
        clase.error_envio = None
    monkeypatch.setattr(es.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(es.smtplib, "SMTP_SSL", FakeSMTPSSL)
    # La contraseña local de la PC va a una carpeta temporal, nunca a APPDATA.
    monkeypatch.setattr(es, "ruta_secreto", lambda: tmp_path / "smtp_password.dat")


@pytest.fixture
def db(tmp_path):
    base = DatabaseManager(str(tmp_path / "correo.db"))
    base.initialize()
    yield base
    base.close()


@pytest.fixture
def documentos(tmp_path):
    pdf = tmp_path / "V-00021_2026-10-31.pdf"
    xml = tmp_path / "V-00021_2026-10-31.xml"
    pdf.write_bytes(b"%PDF-1.4 prueba")
    xml.write_text("<FacturaElectronica/>", encoding="utf-8")
    return {"pdf": str(pdf), "xml": str(xml), "carpeta": str(tmp_path)}


def _venta(**extra):
    datos = dict(invoice_number="V-00021", client_name="Juan Pérez",
                 created_at="2026-10-31 10:00:00")
    datos.update(extra)
    return SimpleNamespace(**datos)


def _cfg(**extra):
    cfg = {"activo": True, "host": "smtp.ejemplo.com", "port": 587,
           "seguridad": "starttls", "usuario": "facturas@laloma.cr",
           "remitente": "facturas@laloma.cr", "password": "secreta-123"}
    cfg.update(extra)
    return cfg


# ---------- validación ----------

@pytest.mark.parametrize("valor", [
    "cliente@correo.com", "ana.mora+fe@gmail.com", "o'brien@empresa.co.cr"])
def test_correos_validos(valor):
    assert es.correo_valido(valor)


@pytest.mark.parametrize("valor", [
    "", "   ", "sin-arroba", "a@b", "a@b.com, otro@c.com", "a@b.com otro@c.com",
    "a@b.com\nBcc: robo@mal.com", "a@b.com\r\nSubject: x", "@b.com", None])
def test_correos_invalidos_o_con_inyeccion(valor):
    assert not es.correo_valido(valor)


# ---------- configuración ----------

def test_config_ida_y_vuelta_con_password_local(db, tmp_path):
    es.guardar_config_correo(db, True, "smtp.ejemplo.com", 465, "ssl",
                             "facturas@laloma.cr", "", password="clave-1")
    cfg = es.cargar_config_correo(db)
    assert cfg["activo"] and cfg["host"] == "smtp.ejemplo.com"
    assert cfg["port"] == 465 and cfg["seguridad"] == "ssl"
    assert cfg["usuario"] == cfg["remitente"] == "facturas@laloma.cr"
    assert cfg["password"] == "clave-1"
    # La contraseña NO está en la base compartida.
    filas = db.execute_query("SELECT key, value FROM app_config")
    assert not any("clave-1" in str(f["value"]) for f in filas)
    assert (tmp_path / "smtp_password.dat").is_file()


def test_password_vacia_conserva_la_existente(db):
    es.guardar_config_correo(db, True, "h.com", 587, "starttls", "u@h.com", "",
                             password="original")
    es.guardar_config_correo(db, False, "h.com", 587, "starttls", "u@h.com", "",
                             password="")
    cfg = es.cargar_config_correo(db)
    assert cfg["password"] == "original"
    assert cfg["activo"] is False


def test_valores_por_defecto_y_seguridad_invalida(db):
    cfg = es.cargar_config_correo(db)
    assert cfg["activo"] is False and cfg["seguridad"] == "starttls"
    assert cfg["port"] == 587 and cfg["password"] == ""
    es.guardar_config_correo(db, True, "h.com", "no-es-numero", "ninguna",
                             "u@h.com", "")
    cfg = es.cargar_config_correo(db)
    assert cfg["seguridad"] == "starttls" and cfg["port"] == 587


def test_config_completa():
    assert es.config_completa(_cfg())
    assert not es.config_completa(_cfg(host=""))
    assert not es.config_completa(_cfg(password=""))
    assert not es.config_completa(_cfg(remitente="no-es-correo", usuario=""))


# ---------- cuándo se envía ----------

def test_motivo_no_envio(documentos):
    cliente = "cliente@correo.com"
    assert es.motivo_no_envio(_cfg(), cliente, documentos) == ""
    assert es.motivo_no_envio(_cfg(activo=False), cliente, documentos) == "desactivado"
    sin_xml = dict(documentos, xml=None)
    assert es.motivo_no_envio(_cfg(), cliente, sin_xml) == "no_electronica"
    assert es.motivo_no_envio(_cfg(), cliente, None) == "no_electronica"
    assert es.motivo_no_envio(_cfg(), "", documentos) == "sin_correo_cliente"
    assert es.motivo_no_envio(_cfg(), "malo@", documentos) == "sin_correo_cliente"
    assert es.motivo_no_envio(_cfg(host=""), cliente, documentos) == "config_incompleta"


# ---------- envío ----------

def test_envio_starttls_con_pdf_y_xml(documentos):
    ok, mensaje = es.enviar_factura(
        _cfg(), COMPANY, _venta(), "cliente@correo.com", documentos,
        clave="50631102600310112345600100001010000000021100000001")
    assert ok, mensaje
    smtp = FakeSMTP.instancias[0]
    assert (smtp.host, smtp.port) == ("smtp.ejemplo.com", 587)
    assert smtp.acciones == ["ehlo", "starttls", "ehlo",
                             ("login", "facturas@laloma.cr", "secreta-123")]
    # Conexión cifrada con verificación de certificado.
    assert isinstance(smtp.context_tls, ssl.SSLContext)
    assert smtp.context_tls.verify_mode == ssl.CERT_REQUIRED
    assert smtp.context_tls.check_hostname

    msg = smtp.mensajes[0]
    assert msg["To"] == "cliente@correo.com"
    assert "facturas@laloma.cr" in msg["From"] and "Muebleria La Loma" in msg["From"]
    assert msg["Subject"] == "Factura electrónica V-00021 - Muebleria La Loma"
    assert msg["Reply-To"] == "info@laloma.cr"
    nombres = sorted(p.get_filename() for p in msg.iter_attachments())
    assert nombres == ["V-00021_2026-10-31.pdf", "V-00021_2026-10-31.xml"]
    cuerpo = msg.get_body().get_content()
    assert "Juan Pérez" in cuerpo and "5063110260031011234560010000101" in cuerpo


def test_envio_ssl_directo(documentos):
    ok, _ = es.enviar_factura(
        _cfg(seguridad="ssl", port=465), COMPANY, _venta(),
        "cliente@correo.com", documentos)
    assert ok
    assert not FakeSMTP.instancias
    smtp = FakeSMTPSSL.instancias[0]
    assert smtp.port == 465
    assert isinstance(smtp.context, ssl.SSLContext)
    assert "starttls" not in smtp.acciones
    assert len(smtp.mensajes) == 1


def test_envio_sin_login_si_no_hay_usuario(documentos):
    ok, _ = es.enviar_factura(
        _cfg(usuario="", password="", remitente="facturas@laloma.cr"),
        COMPANY, _venta(), "cliente@correo.com", documentos)
    assert ok
    assert not any(isinstance(a, tuple) for a in FakeSMTP.instancias[0].acciones)


def test_error_de_autenticacion_no_filtra_la_password(documentos):
    FakeSMTP.error_login = smtplib.SMTPAuthenticationError(535, b"bad creds")
    ok, mensaje = es.enviar_factura(
        _cfg(), COMPANY, _venta(), "cliente@correo.com", documentos)
    assert not ok
    assert "contraseña" in mensaje.lower()
    assert "secreta-123" not in mensaje


@pytest.mark.parametrize("error,fragmento", [
    (smtplib.SMTPRecipientsRefused({"x@y.com": (550, b"no")}), "correo del cliente"),
    (TimeoutError(), "tardó demasiado"),
    (ConnectionRefusedError(), "rechazó la conexión"),
    (OSError("sin red"), "No hay conexión"),
    (ssl.SSLError("fallo"), "conexión segura"),
])
def test_errores_devuelven_mensaje_claro_sin_lanzar(documentos, error, fragmento):
    FakeSMTP.error_envio = error
    ok, mensaje = es.enviar_factura(
        _cfg(), COMPANY, _venta(), "cliente@correo.com", documentos)
    assert not ok and fragmento in mensaje


def test_sin_archivos_para_adjuntar():
    ok, mensaje = es.enviar_factura(
        _cfg(), COMPANY, _venta(), "cliente@correo.com",
        {"pdf": "/no/existe.pdf", "xml": None})
    assert not ok and "archivos" in mensaje
    assert not FakeSMTP.instancias


def test_nombre_de_cliente_con_saltos_de_linea_no_rompe_encabezados(documentos):
    venta = _venta(invoice_number="V-1\nBcc: robo@mal.com",
                   client_name="Juan\r\nBcc: robo@mal.com")
    ok, mensaje = es.enviar_factura(
        _cfg(), COMPANY, venta, "cliente@correo.com", documentos)
    assert ok, mensaje
    msg = FakeSMTP.instancias[0].mensajes[0]
    assert msg["Bcc"] is None
    assert "\n" not in msg["Subject"] and "\r" not in msg["Subject"]


def test_adjunto_demasiado_grande(documentos, monkeypatch):
    monkeypatch.setattr(es, "MAX_ADJUNTO_BYTES", 5)
    ok, mensaje = es.enviar_factura(
        _cfg(), COMPANY, _venta(), "cliente@correo.com", documentos)
    assert not ok and "demasiado grande" in mensaje


def test_correo_de_prueba():
    ok, mensaje = es.enviar_prueba(_cfg(), COMPANY, "yo@laloma.cr")
    assert ok, mensaje
    msg = FakeSMTP.instancias[0].mensajes[0]
    assert msg["To"] == "yo@laloma.cr" and "Prueba" in msg["Subject"]
    assert list(msg.iter_attachments()) == []

    ok, mensaje = es.enviar_prueba(_cfg(), COMPANY, "malo")
    assert not ok and "válido" in mensaje
    ok, mensaje = es.enviar_prueba(_cfg(host=""), COMPANY, "yo@laloma.cr")
    assert not ok and "Complete" in mensaje


@pytest.mark.parametrize("faltante", ["pdf", "xml"])
def test_no_envia_factura_con_un_adjunto_faltante(documentos, faltante):
    Path(documentos[faltante]).unlink()
    ok, mensaje = es.enviar_factura(
        _cfg(), COMPANY, _venta(), "cliente@correo.com", documentos)
    assert not ok and "PDF y el XML" in mensaje
    assert not FakeSMTP.instancias


@pytest.mark.parametrize("destino", ["", "a@b.com,otro@c.com",
                                      "a@b.com\nBcc: otro@c.com"])
def test_envio_valida_destinatario_antes_de_conectar(documentos, destino):
    ok, mensaje = es.enviar_factura(_cfg(), COMPANY, _venta(), destino, documentos)
    assert not ok and "válido" in mensaje
    assert not FakeSMTP.instancias


def test_envio_valida_configuracion_antes_de_conectar(documentos):
    ok, mensaje = es.enviar_factura(
        _cfg(password=""), COMPANY, _venta(), "cliente@correo.com", documentos)
    assert not ok and "Complete" in mensaje
    assert not FakeSMTP.instancias


def test_fallo_al_guardar_password_revierte_configuracion(db, monkeypatch):
    es.guardar_config_correo(db, False, "smtp.original.com", 587, "starttls",
                             "original@laloma.cr", "", password="original")

    def fallar(_password):
        raise OSError("Sin permiso de escritura")

    monkeypatch.setattr(es, "guardar_password", fallar)
    with pytest.raises(OSError):
        es.guardar_config_correo(db, True, "smtp.nuevo.com", 465, "ssl",
                                 "nuevo@laloma.cr", "", password="nueva")
    cfg = es.cargar_config_correo(db)
    assert cfg["host"] == "smtp.original.com"
    assert cfg["activo"] is False
    assert cfg["password"] == "original"


@pytest.fixture
def widget_correo(db):
    from PyQt6.QtWidgets import QApplication
    from main import build_services
    from modules.settings.settings_widget import SettingsWidget

    app = QApplication.instance() or QApplication([])
    widget = SettingsWidget(build_services(db))
    yield widget
    widget.deleteLater()
    app.processEvents()


def test_guardar_muestra_fallo_de_correo_sin_anunciar_exito(widget_correo, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox

    avisos, exitos = [], []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: avisos.append(args[2]))
    monkeypatch.setattr(QMessageBox, "information", lambda *args: exitos.append(args[2]))

    def fallar(*args, **kwargs):
        raise OSError("Sin permiso de escritura")

    monkeypatch.setattr(es, "guardar_config_correo", fallar)
    widget_correo.smtp_password_input.setText("conservar-al-fallar")
    widget_correo._save()
    assert len(avisos) == 1 and "correo" in avisos[0]
    assert not exitos
    assert widget_correo.smtp_password_input.text() == "conservar-al-fallar"


def test_no_activa_envio_sin_configuracion_completa(widget_correo, db, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox

    avisos = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: avisos.append(args[2]))
    widget_correo.email_auto_check.setChecked(True)
    assert widget_correo._save_correo() is False
    assert avisos and "Complete" in avisos[0]
    assert es.cargar_config_correo(db)["activo"] is False


def test_al_volver_a_configuracion_recarga_correo_compartido(widget_correo, db):
    es.guardar_config_correo(db, True, "smtp.nuevo.com", 465, "ssl",
                             "otra-caja@laloma.cr", "", password="prueba")
    widget_correo._load_config()
    assert widget_correo.email_auto_check.isChecked()
    assert widget_correo.smtp_host_input.text() == "smtp.nuevo.com"
    assert widget_correo.smtp_port_input.text() == "465"
    assert widget_correo.smtp_security_combo.currentData() == "ssl"
    assert widget_correo.smtp_user_input.text() == "otra-caja@laloma.cr"


def test_pos_envia_en_hilo_y_audita_en_interfaz(widget_correo, db, documentos, monkeypatch):
    import threading
    import time
    from PyQt6.QtTest import QTest
    from modules.pos.pos_widget import POSWidget

    pos = POSWidget(widget_correo.services)
    pos.client = SimpleNamespace(email="primero@correo.com")
    es.guardar_config_correo(db, True, "smtp.ejemplo.com", 587, "starttls",
                             "facturas@laloma.cr", "", password="prueba")
    iniciado, continuar, terminado = (threading.Event() for _ in range(3))
    envios = []

    def enviar(cfg, company, sale, destino, archivos, clave):
        iniciado.set()
        continuar.wait(5)
        envios.append((threading.get_ident(), destino))
        terminado.set()
        return True, "Factura enviada"

    monkeypatch.setattr(es, "enviar_factura", enviar)
    try:
        pos._enviar_correo_automatico(_venta(), COMPANY, documentos, "clave-prueba")
        assert iniciado.wait(2), "el POS no inició el envío"
        assert not terminado.is_set(), "el cobro esperó al servidor SMTP"
        pos.client = SimpleNamespace(email="siguiente@correo.com")
        continuar.set()
        limite = time.monotonic() + 3
        filas = []
        while time.monotonic() < limite:
            QTest.qWait(10)
            filas = db.execute_query(
                "SELECT detail FROM audit_log WHERE event = 'FACTURA_CORREO'")
            if filas:
                break
        assert len(envios) == 1
        assert envios[0][1] == "primero@correo.com"
        assert envios[0][0] != threading.get_ident()
        assert len(filas) == 1 and "primero@correo.com" in filas[0]["detail"]
    finally:
        continuar.set()
        terminado.wait(2)
        pos.deleteLater()


def test_config_correo_compartida_sin_password_en_servidor(servidor_aislado):
    import threading
    from network.remote_db import RemoteDatabase
    from server import start_server

    servidor = start_server(port=0)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    remoto = RemoteDatabase(
        f"http://127.0.0.1:{servidor.server_address[1]}", station="PRUEBA")
    try:
        remoto.setup("Prueba", "1234")
        es.guardar_config_correo(remoto, True, "smtp.ejemplo.com", 587, "starttls",
                                 "facturas@laloma.cr", "", password="clave-local-lan")
        cfg = es.cargar_config_correo(remoto)
        assert cfg["activo"] and cfg["host"] == "smtp.ejemplo.com"
        assert cfg["password"] == "clave-local-lan"
        filas = remoto.execute_query("SELECT key, value FROM app_config")
        assert not any("clave-local-lan" in str(f["value"]) for f in filas)
    finally:
        remoto.logout()
        servidor.shutdown()
        hilo.join(timeout=2)
        servidor.close_transactions()
        servidor.server_close()
