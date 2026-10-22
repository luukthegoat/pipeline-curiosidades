// Lanzador de «Mente Inquieta.exe»: abre el menú (menu\aplicacion.py) en su propia ventana,
// con el Python del entorno .venv y sin consola. Se compila con lanzador\crear_exe.bat.
using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

static class MenteInquieta
{
    [STAThread]
    static void Main()
    {
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
                "Mente Inquieta", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return;
        }

        var inicio = new ProcessStartInfo(python, "\"" + script + "\"")
        {
            WorkingDirectory = raiz,
            UseShellExecute = false,
            CreateNoWindow = true,
        };
        Process.Start(inicio);
    }
}
