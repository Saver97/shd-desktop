// Small desktop-menu entry point. It avoids unpacking the PyInstaller bundle
// merely to send a command to an already running SHD Desktop process.
using System;
using System.Diagnostics;
using System.IO;
using System.IO.Pipes;
using System.Security.Cryptography;
using System.Text;

internal static class SHDQuick
{
    private static string PipeName()
    {
        string home = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile)
            .ToLowerInvariant();
        byte[] bytes = Encoding.UTF8.GetBytes(home);
        using (SHA256 hash = SHA256.Create())
        {
            byte[] digest = hash.ComputeHash(bytes);
            StringBuilder name = new StringBuilder("SHDDesktop-");
            for (int index = 0; index < 8; index++)
                name.Append(digest[index].ToString("x2"));
            return name.ToString();
        }
    }

    private static bool Forward(string command)
    {
        try
        {
            using (NamedPipeClientStream pipe = new NamedPipeClientStream(
                ".", PipeName(), PipeDirection.Out))
            {
                pipe.Connect(200);
                byte[] payload = Encoding.ASCII.GetBytes(command + "\n");
                pipe.Write(payload, 0, payload.Length);
                pipe.Flush();
                return true;
            }
        }
        catch (IOException) { return false; }
        catch (TimeoutException) { return false; }
        catch (UnauthorizedAccessException) { return false; }
    }

    private static int Main(string[] args)
    {
        string action = args.Length > 0 ? args[0] : "center";
        if (action != "note" && action != "center" && action != "probe")
            return 2;
        if (Forward(action == "probe" ? "probe" : action))
            return 0;
        if (action == "probe")
            return 1;
        try
        {
            string main = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "SHDDesktop.exe");
            Process.Start(new ProcessStartInfo(main,
                action == "note" ? "--new-note" : "--show-center")
            {
                UseShellExecute = false,
                WorkingDirectory = AppDomain.CurrentDomain.BaseDirectory
            });
            return 0;
        }
        catch (Exception)
        {
            return 3;
        }
    }
}
