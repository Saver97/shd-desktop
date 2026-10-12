// Single-file public entry point. The Qt/Python bundle is an embedded resource;
// running instances receive desktop actions before that bundle is touched.
using System;
using System.Diagnostics;
using System.IO;
using System.IO.Pipes;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Threading;

internal static class SHDLauncher
{
    private const string PayloadHash = "__PAYLOAD_SHA256__";
    private const string PayloadResource = "SHD.Payload";

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int MessageBox(IntPtr window, string message, string title, uint flags);

    private static string PipeName()
    {
        byte[] bytes = Encoding.UTF8.GetBytes(
            Environment.GetFolderPath(Environment.SpecialFolder.UserProfile).ToLowerInvariant());
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

    private static string FileHash(string path)
    {
        using (SHA256 hash = SHA256.Create())
        using (FileStream stream = File.OpenRead(path))
            return BitConverter.ToString(hash.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
    }

    private static string EnsureCore()
    {
        string directory = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "SHDDesktop", "Runtime", PayloadHash.Substring(0, 16));
        string core = Path.Combine(directory, "SHDDesktopCore.exe");
        Directory.CreateDirectory(directory);
        using (Mutex mutex = new Mutex(false, @"Local\SHDDesktop-Extract-" + PayloadHash.Substring(0, 16)))
        {
            bool acquired;
            try { acquired = mutex.WaitOne(TimeSpan.FromSeconds(60)); }
            catch (AbandonedMutexException) { acquired = true; }
            if (!acquired)
                throw new TimeoutException("等待程序解包超时");
            try
            {
                if (File.Exists(core) && FileHash(core) == PayloadHash)
                    return core;
                string temporary = Path.Combine(directory, Guid.NewGuid().ToString("N") + ".tmp");
                try
                {
                    using (Stream source = Assembly.GetExecutingAssembly()
                        .GetManifestResourceStream(PayloadResource))
                    {
                        if (source == null)
                            throw new InvalidDataException("安装包缺少程序资源");
                        using (FileStream target = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write))
                            source.CopyTo(target);
                    }
                    if (FileHash(temporary) != PayloadHash)
                        throw new InvalidDataException("程序资源校验失败");
                    if (File.Exists(core))
                        File.Delete(core);
                    File.Move(temporary, core);
                }
                finally
                {
                    if (File.Exists(temporary))
                        File.Delete(temporary);
                }
                return core;
            }
            finally { mutex.ReleaseMutex(); }
        }
    }

    private static int Main(string[] args)
    {
        string argument = args.Length == 0 ? "" : args[0];
        if (args.Length > 1 || (argument != "" && argument != "--show-center"
            && argument != "--new-note" && argument != "--restore-desktop-icons"
            && argument != "--smoke" && argument != "--help" && argument != "--probe"))
            return 2;
        string request = argument == "--new-note" ? "note" : "center";
        if (argument == "--probe")
            return Forward("probe") ? 0 : 1;
        if (argument == "" || argument == "--show-center" || argument == "--new-note")
        {
            if (Forward(request))
                return 0;
        }
        try
        {
            ProcessStartInfo start = new ProcessStartInfo(EnsureCore(), argument)
            {
                UseShellExecute = false,
                WorkingDirectory = AppDomain.CurrentDomain.BaseDirectory
            };
            start.EnvironmentVariables["SHD_PUBLIC_EXE"] = Assembly.GetExecutingAssembly().Location;
            using (Process process = Process.Start(start))
            {
                if (argument == "--smoke" || argument == "--help"
                    || argument == "--restore-desktop-icons")
                {
                    process.WaitForExit();
                    return process.ExitCode;
                }
            }
            return 0;
        }
        catch (Exception error)
        {
            MessageBox(IntPtr.Zero, error.Message, "SHD Desktop 启动失败", 0x10);
            return 3;
        }
    }
}
