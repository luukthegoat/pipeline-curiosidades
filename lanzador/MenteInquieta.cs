// Lanzador de «Mente Inquieta.exe»: abre el menú (menu\aplicacion.py) en su propia ventana,
// con el Python del entorno .venv y sin consola. Se compila con lanzador\crear_exe.bat.
//
// - Si la aplicación ya está abierta, solo trae su ventana al frente.
// - Mientras Python arranca (unos segundos), muestra al momento una pequeña pantalla de carga.
using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Runtime.InteropServices;
using System.Windows.Forms;

static class MenteInquieta
{
    const string Titulo = "Mente Inquieta";

    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern IntPtr FindWindow(string clase, string titulo);
    [DllImport("user32.dll")] static extern bool ShowWindow(IntPtr ventana, int modo);
    [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr ventana);
    [DllImport("user32.dll")] static extern bool SetProcessDPIAware();

    [STAThread]
    static void Main()
    {
        // ¿Ya está abierta? Lo dice el mutex que crea la aplicación (menu\aplicacion.py), no el título de una
        // ventana: una pestaña del navegador con el menú también se llama «Mente Inquieta».
        System.Threading.Mutex abierta;
        if (System.Threading.Mutex.TryOpenExisting("MenteInquieta.Menu", out abierta))
        {
            abierta.Dispose();
            IntPtr ventana = FindWindow(null, Titulo);
            if (ventana != IntPtr.Zero)
            {
                ShowWindow(ventana, 9);  // SW_RESTORE: por si está minimizada
                SetForegroundWindow(ventana);
            }
            return;
        }

        string raiz = AppDomain.CurrentDomain.BaseDirectory;
        string python = Path.Combine(raiz, @".venv\Scripts\pythonw.exe");
        string script = Path.Combine(raiz, @"menu\aplicacion.py");
        if (!File.Exists(python) || !File.Exists(script))
        {
            MessageBox.Show(
                "No encuentro el programa junto a este .exe.\n\n" +
                "«Mente Inquieta.exe» tiene que estar en la carpeta principal del proyecto, con el entorno creado:\n" +
                "    python -m venv .venv\n" +
                "    .venv\\Scripts\\pip install -r requirements.txt",
                Titulo, MessageBoxButtons.OK, MessageBoxIcon.Error);
            return;
        }

        var inicio = new ProcessStartInfo(python, "\"" + script + "\"")
        {
            WorkingDirectory = raiz,
            UseShellExecute = false,
            CreateNoWindow = true,
        };
        Process proceso = Process.Start(inicio);

        SetProcessDPIAware();
        Application.EnableVisualStyles();
        Application.Run(new PantallaDeCarga(Path.Combine(raiz, @"menu\static\logo.png"), proceso));
    }

    // Ventanita sin bordes con el logo; se cierra sola cuando aparece la ventana de la aplicación.
    class PantallaDeCarga : Form
    {
        readonly Process proceso;
        readonly DateTime desde = DateTime.Now;
        readonly Timer reloj = new Timer { Interval = 100 };
        int avance;

        public PantallaDeCarga(string logo, Process proceso)
        {
            this.proceso = proceso;
            float escala = DeviceDpi / 96f;
            FormBorderStyle = FormBorderStyle.None;
            StartPosition = FormStartPosition.CenterScreen;
            ClientSize = new Size((int)(300 * escala), (int)(190 * escala));
            BackColor = Color.FromArgb(13, 15, 21);
            ShowInTaskbar = false;
            TopMost = true;
            DoubleBuffered = true;
            Text = "Abriendo " + Titulo;

            var imagen = new PictureBox
            {
                SizeMode = PictureBoxSizeMode.Zoom,
                Size = new Size((int)(64 * escala), (int)(64 * escala)),
                Location = new Point((ClientSize.Width - (int)(64 * escala)) / 2, (int)(36 * escala)),
                BackColor = Color.Transparent,
            };
            if (File.Exists(logo)) imagen.Image = Image.FromFile(logo);
            Controls.Add(imagen);

            Controls.Add(new Label
            {
                Text = "Abriendo Mente Inquieta…",
                ForeColor = Color.FromArgb(155, 161, 174),
                Font = new Font("Segoe UI", 10f),
                TextAlign = ContentAlignment.MiddleCenter,
                Size = new Size(ClientSize.Width, (int)(30 * escala)),
                Location = new Point(0, (int)(132 * escala)),
            });

            reloj.Tick += (s, e) =>
            {
                avance = (avance + 6) % 140;
                Invalidate(new Rectangle(0, (int)(116 * escala), ClientSize.Width, (int)(8 * escala)));
                bool lista = FindWindow(null, Titulo) != IntPtr.Zero;
                if (lista || proceso.HasExited || (DateTime.Now - desde).TotalSeconds > 40) Close();
            };
            reloj.Start();
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            base.OnPaint(e);
            float escala = DeviceDpi / 96f;
            int ancho = (int)(120 * escala), x = (ClientSize.Width - ancho) / 2, y = (int)(118 * escala);
            using (var fondo = new SolidBrush(Color.FromArgb(36, 41, 54)))
                e.Graphics.FillRectangle(fondo, x, y, ancho, (int)(3 * escala));
            int trozo = ancho * 2 / 5, pos = x - trozo + (ancho + trozo) * avance / 140;
            var visible = Rectangle.Intersect(new Rectangle(pos, y, trozo, (int)(3 * escala)), new Rectangle(x, y, ancho, (int)(3 * escala)));
            using (var dorado = new SolidBrush(Color.FromArgb(255, 196, 0)))
                e.Graphics.FillRectangle(dorado, visible);
            using (var borde = new Pen(Color.FromArgb(36, 41, 54)))
                e.Graphics.DrawRectangle(borde, 0, 0, ClientSize.Width - 1, ClientSize.Height - 1);
        }
    }
}
