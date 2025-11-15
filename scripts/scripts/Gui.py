import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import serial
import serial.tools.list_ports
import threading
import time
from collections import deque
import csv

APP_TITLE = "Aperiodic Pulse Generator - GUI Control"

class ArduinoApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.ser = None
        self.running = False

        # ===== Connection frame =====
        frame_conn = ttk.LabelFrame(root, text="Konekcija")
        frame_conn.pack(fill="x", padx=10, pady=5)

        ttk.Label(frame_conn, text="Serijski port:").grid(row=0, column=0, sticky="w")
        self.port_cb = ttk.Combobox(frame_conn, values=self.get_serial_ports(), width=20)
        self.port_cb.grid(row=0, column=1, padx=5)
        if self.port_cb['values']:
            self.port_cb.current(0)

        self.btn_refresh = ttk.Button(frame_conn, text="Osveži", command=self.refresh_ports)
        self.btn_refresh.grid(row=0, column=2, padx=5)

        self.btn_connect = ttk.Button(frame_conn, text="Poveži", command=self.connect)
        self.btn_connect.grid(row=0, column=3, padx=5)
        self.btn_disconnect = ttk.Button(frame_conn, text="Prekini", command=self.disconnect, state="disabled")
        self.btn_disconnect.grid(row=0, column=4, padx=5)

        # ===== Parameters frame =====
        frame_params = ttk.LabelFrame(root, text="Parametri")
        frame_params.pack(fill="x", padx=10, pady=5)

        ttk.Label(frame_params, text="Lambda (Hz):").grid(row=0, column=0, sticky="w")
        self.lambda_var = tk.DoubleVar(value=2.0)
        self.lambda_entry = ttk.Entry(frame_params, textvariable=self.lambda_var, width=10)
        self.lambda_entry.grid(row=0, column=1, padx=5)

        ttk.Label(frame_params, text="Min širina (µs):").grid(row=1, column=0, sticky="w")
        self.min_width_var = tk.IntVar(value=50)
        self.min_width_entry = ttk.Entry(frame_params, textvariable=self.min_width_var, width=10)
        self.min_width_entry.grid(row=1, column=1, padx=5)

        ttk.Label(frame_params, text="Max širina (µs):").grid(row=2, column=0, sticky="w")
        self.max_width_var = tk.IntVar(value=1000)
        self.max_width_entry = ttk.Entry(frame_params, textvariable=self.max_width_var, width=10)
        self.max_width_entry.grid(row=2, column=1, padx=5)

        self.btn_send = ttk.Button(frame_params, text="Pošalji parametre", command=self.send_params, state="disabled")
        self.btn_send.grid(row=3, column=0, columnspan=2, pady=5)

        # ===== Log frame =====
        frame_log = ttk.LabelFrame(root, text="Log")
        frame_log.pack(fill="both", expand=True, padx=10, pady=5)
        self.text_log = tk.Text(frame_log, height=16)
        self.text_log.pack(fill="both", expand=True)

        # ===== Stats frame =====
        frame_stats = ttk.LabelFrame(root, text="Statistika")
        frame_stats.pack(fill="x", padx=10, pady=5)
        self.stats_label = ttk.Label(frame_stats, text="Broj impulsa: 0 | Prosečna širina: 0 µs | Frekvencija: 0 Hz")
        self.stats_label.pack()

        # ===== Save log button =====
        frame_save = ttk.Frame(root)
        frame_save.pack(fill="x", padx=10, pady=5)
        self.btn_save_csv = ttk.Button(frame_save, text="Sačuvaj log u CSV", command=self.save_log_csv)
        self.btn_save_csv.pack(side="right")

        # Threading & stats
        self.thread = None
        self.pulse_count = 0
        self.pulse_widths = []
        self.pulse_times = deque()
        self.log_rows = []  # for CSV export

    def get_serial_ports(self):
        ports = serial.tools.list_ports.comports()
        return [port.device for port in ports]

    def refresh_ports(self):
        self.port_cb["values"] = self.get_serial_ports()
        if self.port_cb["values"]:
            self.port_cb.current(0)

    def connect(self):
        port = self.port_cb.get()
        if not port:
            messagebox.showwarning("Upozorenje", "Izaberite serijski port")
            return
        try:
            self.ser = serial.Serial(port, 9600, timeout=1)
            self.running = True
            self.thread = threading.Thread(target=self.read_serial, daemon=True)
            self.thread.start()
            self.btn_connect.config(state="disabled")
            self.btn_disconnect.config(state="normal")
            self.btn_send.config(state="normal")
            self.log(f"Povezan na {port}")
        except Exception as e:
            messagebox.showerror("Greška", f"Ne mogu da se povežem: {e}")

    def disconnect(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1)
        if self.ser and self.ser.is_open:
            self.ser.close()
        self.btn_connect.config(state="normal")
        self.btn_disconnect.config(state="disabled")
        self.btn_send.config(state="disabled")
        self.log("Prekinuta veza")

    def send_params(self):
        try:
            lam = self.lambda_var.get()
            minw = self.min_width_var.get()
            maxw = self.max_width_var.get()
            if minw > maxw:
                messagebox.showerror("Greška", "Min širina ne može biti veća od max širine")
                return
            cmd = f"LAMBDA:{lam};MINW:{minw};MAXW:{maxw}\n"
            self.ser.write(cmd.encode('utf-8'))
            self.log(f"Poslato: {cmd.strip()}")
        except Exception as e:
            messagebox.showerror("Greška", f"Greška pri slanju parametara: {e}")

    def read_serial(self):
        while self.running and self.ser and self.ser.is_open:
            try:
                line = self.ser.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    self.log(f"Arduino: {line}")
                    self.update_stats_from_line(line)
            except Exception as e:
                self.log(f"Greška pri čitanju: {e}")
                break

    def update_stats_from_line(self, line):
        # Expected line: "Impuls @ <ms> ms | širina: <us> µs | sledeći razmak: <ms> ms"
        if line.startswith("Arduino:"):
            # strip "Arduino: "
            msg = line.split("Arduino:",1)[1].strip()
        else:
            msg = line

        if msg.startswith("Impuls @"):
            try:
                parts = [p.strip() for p in msg.split("|")]
                t_ms = int(parts[0].split("@")[1].strip().split()[0])
                width_us = int(parts[1].split(":")[1].strip().split()[0])
                gap_ms = int(parts[2].split(":")[1].strip().split()[0])

                self.pulse_count += 1
                self.pulse_widths.append(width_us)
                now_sec = time.time()
                self.pulse_times.append(now_sec)
                self.log_rows.append([t_ms, width_us, gap_ms])

                while self.pulse_times and (now_sec - self.pulse_times[0] > 5.0):
                    self.pulse_times.popleft()

                avg_width = sum(self.pulse_widths) / len(self.pulse_widths)
                freq = len(self.pulse_times) / 5.0

                self.root.after(0, lambda: self.stats_label.config(
                    text=f"Broj impulsa: {self.pulse_count} | Prosečna širina: {avg_width:.1f} µs | Frekvencija: {freq:.2f} Hz"
                ))
            except Exception as e:
                self.log(f"Greška u parsiranju: {e}")

    def save_log_csv(self):
        if not self.log_rows:
            messagebox.showinfo("Informacija", "Nema podataka za snimanje.")
            return
        fp = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not fp:
            return
        try:
            with open(fp, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["timestamp_ms","pulse_width_us","next_gap_ms"])
                w.writerows(self.log_rows)
            messagebox.showinfo("Uspeh", f"Log sačuvan u: {fp}")
        except Exception as e:
            messagebox.showerror("Greška", f"Ne mogu da sačuvam CSV: {e}")

    def log(self, message):
        self.text_log.insert(tk.END, message + "\n")
        self.text_log.see(tk.END)

def main():
    root = tk.Tk()
    app = ArduinoApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
