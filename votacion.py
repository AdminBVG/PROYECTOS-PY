import os
import pandas as pd
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
# Asegúrate de tener matplotlib instalado: pip install matplotlib
try:
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

class VotacionApp:
    def __init__(self, root):
        self.root = root
        root.title("Registro de Asistencia y Votaciones")
        self.df_original = pd.DataFrame()
        self.quorum_min = 50.0  # Porcentaje mínimo por defecto

        # Menú superior
        menubar = tk.Menu(root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Importar Excel", command=self.importar_excel)
        file_menu.add_separator()
        export_menu = tk.Menu(file_menu, tearoff=0)
        export_menu.add_command(label="Exportar a Excel", command=self.export_excel)
        export_menu.add_command(label="Exportar a CSV", command=self.export_csv)
        if HAS_MPL:
            export_menu.add_command(label="Exportar a PDF", command=self.export_pdf)
        file_menu.add_cascade(label="Exportar", menu=export_menu)
        file_menu.add_separator()
        file_menu.add_command(label="Salir", command=root.quit)
        menubar.add_cascade(label="Archivo", menu=file_menu)

        conf_menu = tk.Menu(menubar, tearoff=0)
        conf_menu.add_command(label="Establecer quórum mínimo...", command=self.set_quorum)
        menubar.add_cascade(label="Configuración", menu=conf_menu)

        edit_menu = tk.Menu(menubar, tearoff=0)
        edit_menu.add_command(label="Marcar todos como PRESENCIAL", command=lambda: self.bulk_set('PRESENCIAL'))
        edit_menu.add_command(label="Marcar todos como VIRTUAL", command=lambda: self.bulk_set('VIRTUAL'))
        edit_menu.add_command(label="Marcar todos como AUSENTE", command=lambda: self.bulk_set('AUSENTE'))
        menubar.add_cascade(label="Edición Masiva", menu=edit_menu)

        root.config(menu=menubar)

        # Búsqueda y filtro
        top_frame = ttk.Frame(root)
        top_frame.pack(fill='x', padx=10, pady=5)
        ttk.Label(top_frame, text="Buscar:").pack(side='left')
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(top_frame, textvariable=self.search_var)
        search_entry.pack(side='left', padx=(0,20))
        search_entry.bind("<KeyRelease>", lambda e: self.actualizar_vista())
        ttk.Label(top_frame, text="Filtrar Asistencia:").pack(side='left')
        self.filter_var = tk.StringVar(value="Todos")
        self.filter_cb = ttk.Combobox(
            top_frame,
            textvariable=self.filter_var,
            values=["Todos", "PRESENCIAL", "VIRTUAL", "AUSENTE"],
            state="readonly",
            width=12
        )
        self.filter_cb.pack(side='left', padx=(5,0))
        self.filter_cb.bind("<<ComboboxSelected>>", lambda e: self.actualizar_vista())

        # Resumen arriba
        style = ttk.Style(root)
        style.configure("Quorum.TFrame", background='white')
        self.sum_frame = ttk.Frame(root, style="Quorum.TFrame")
        self.sum_frame.pack(fill='x', padx=10, pady=(0,5))
        ttk.Label(self.sum_frame, text="Resumen de Asistencia", font=('Arial',14,'bold')).pack()
        self.sum_labels = {}
        for status in ["PRESENCIAL", "VIRTUAL", "AUSENTE"]:
            lbl = ttk.Label(self.sum_frame, text=f"{status}: 0 (0.00%)", font=('Arial',12))
            lbl.pack(anchor='w', padx=20)
            self.sum_labels[status] = lbl

        # Tabla principal
        main_frame = ttk.Frame(root)
        main_frame.pack(fill='both', expand=True, padx=10, pady=5)
        self.tree = ttk.Treeview(main_frame, show='headings', selectmode='extended')
        vsb = ttk.Scrollbar(main_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side='left', fill='both', expand=True)
        vsb.pack(side='left', fill='y')

        # Botón guardar
        btn_frame = ttk.Frame(root)
        btn_frame.pack(fill='x', padx=10, pady=5)
        ttk.Button(btn_frame, text="Guardar Cambios", command=self.save_to_excel).pack(side='right')

    def bulk_set(self, status):
        if not hasattr(self, 'ATT_COL'):
            return
        self.df_original[self.ATT_COL] = self.df_original[self.ATT_COL].astype(object)
        self.df_original[self.ATT_COL] = status
        self.actualizar_vista()

    def set_quorum(self):
        val = simpledialog.askfloat(
            "Quórum Mínimo",
            f"Porcentaje mínimo de acciones presentes (actual: {self.quorum_min}%):",
            initialvalue=self.quorum_min,
            minvalue=0.0, maxvalue=100.0
        )
        if val is not None:
            self.quorum_min = val
            self.check_quorum()

    def importar_excel(self):
        path = filedialog.askopenfilename(
            title="Selecciona archivo de votaciones",
            filetypes=[("Excel files","*.xlsx;*.xls")]
        )
        if not path:
            return
        try:
            df = pd.read_excel(path)
        except Exception as e:
            messagebox.showerror("Error al leer Excel", str(e))
            return
        self.input_path = path
        self.df_original = df.copy()
        cols = list(df.columns)
        try:
            self.NO_COL = next(c for c in cols if str(c).strip().upper().startswith("NO"))
            self.ATT_COL = next(c for c in cols if "ASISTENCIA" in c.upper())
            self.ACTIONS_COL = next(c for c in cols if "ACCION" in c.upper())
        except StopIteration:
            messagebox.showerror(
                "Columnas faltantes",
                "El archivo debe contener columnas de número, asistencia y acciones"
            )
            return
        self.df_original[self.ATT_COL] = self.df_original[self.ATT_COL].astype(object)
        self.tree["columns"] = cols
        for c in cols:
            self.tree.heading(c, text=c, command=lambda _c=c: self.sort_by(_c))
            self.tree.column(c, width=50 if c==self.NO_COL else 150, anchor='center')
        self.actualizar_vista()

    def sort_by(self, col):
        self.df_original = self.df_original.sort_values(by=col)
        self.actualizar_vista()

    def actualizar_vista(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        df = self.df_original.copy()
        filt = self.filter_var.get()
        if filt != "Todos":
            df = df[df[self.ATT_COL] == filt]
        term = self.search_var.get().lower().strip()
        if term:
            df = df[df.apply(lambda r: r.astype(str).str.lower().str.contains(term).any(), axis=1)]
        for idx, row in df.iterrows():
            vals = [row[c] for c in self.tree["columns"]]
            self.tree.insert("", "end", iid=str(idx), values=vals)
        self.actualizar_resumen(df)
        self.check_quorum()
        self.tree.bind("<Double-1>", self.on_double_click)

    def actualizar_resumen(self, df):
        total = len(df)
        grp = df.groupby(self.ATT_COL).size()
        for status, lbl in self.sum_labels.items():
            cnt = int(grp.get(status, 0))
            pct = (cnt/total*100) if total else 0
            lbl.config(text=f"{status}: {cnt} ({pct:.2f}%)")

    def check_quorum(self):
        df = self.df_original
        present = df[df[self.ATT_COL].isin(['PRESENCIAL','VIRTUAL'])]
        pct = (len(present)/len(df)*100) if len(df) else 0
        color = 'green' if pct >= self.quorum_min else 'red'
        style = ttk.Style(self.root)
        style.configure("Quorum.TFrame", background=color)
        self.sum_frame.config(style="Quorum.TFrame")

    def on_double_click(self, event):
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        rowid = self.tree.identify_row(event.y)
        colid = self.tree.identify_column(event.x)
        ci = int(colid.replace("#","")) - 1
        colname = self.tree["columns"][ci]
        if colname != self.ATT_COL:
            return
        x,y,w,h = self.tree.bbox(rowid, colid)
        cb = ttk.Combobox(self.root, values=['PRESENCIAL','VIRTUAL','AUSENTE'])
        cb.place(x=x+self.tree.winfo_rootx(), y=y+self.tree.winfo_rooty(), width=w, height=h)
        cb.set(self.tree.set(rowid, colname))
        cb.focus()
        def on_select(e):
            val = cb.get()
            self.tree.set(rowid, colname, val)
            self.df_original.at[int(rowid), colname] = val
            cb.destroy()
            self.actualizar_resumen(self.df_original)
        cb.bind("<<ComboboxSelected>>", on_select)
        cb.bind("<FocusOut>", lambda e: cb.destroy())

    def save_to_excel(self):
        data = [self.tree.item(i)['values'] for i in self.tree.get_children()]
        df_out = pd.DataFrame(data, columns=self.tree['columns'])
        with pd.ExcelWriter(self.input_path, engine='openpyxl', mode='a', if_sheet_exists='replace') as w:
            df_out.to_excel(w, sheet_name=os.path.splitext(os.path.basename(self.input_path))[0], index=False)
        messagebox.showinfo("Guardado", f"Datos guardados en:\n{os.path.abspath(self.input_path)}")

    def export_excel(self):
        out = os.path.splitext(self.input_path)[0] + '_export.xlsx'
        data = [self.tree.item(i)['values'] for i in self.tree.get_children()]
        pd.DataFrame(data, columns=self.tree['columns']).to_excel(out, index=False)
        messagebox.showinfo("Exportado", f"Exportado a Excel:\n{out}")

    def export_csv(self):
        out = os.path.splitext(self.input_path)[0] + '_export.csv'
        data = [self.tree.item(i)['values'] for i in self.tree.get_children()]
        pd.DataFrame(data, columns=self.tree['columns']).to_csv(out, index=False)
        messagebox.showinfo("Exportado", f"Exportado a CSV:\n{out}")

    def export_pdf(self):
        if not HAS_MPL:
            messagebox.showerror("Exportar PDF", "Instala matplotlib para exportar PDF: pip install matplotlib")
            return
        out = os.path.splitext(self.input_path)[0] + '_export.pdf'
        data = [self.tree.item(i)['values'] for i in self.tree.get_children()]
        df_out = pd.DataFrame(data, columns=self.tree['columns'])
        with PdfPages(out) as pdf:
            fig1, ax1 = plt.subplots()
            counts = df_out[self.ATT_COL].value_counts()
            ax1.pie(counts, labels=counts.index, autopct='%1.2f%%')
            ax1.set_title('Distribución de Asistencia')
            pdf.savefig(fig1)
            plt.close(fig1)
            fig2, ax2 = plt.subplots()
            sums = pd.to_numeric(df_out[self.ACTIONS_COL], errors='coerce').fillna(0)
            bars = [sums[df_out[self.ATT_COL]==s].sum() for s in counts.index]
            ax2.bar(counts.index, bars)
            ax2.set_title('Total de Acciones por Tipo')
            plt.xticks(rotation=45)
            pdf.savefig(fig2)
            plt.close(fig2)

if __name__ == "__main__":
    root = tk.Tk()
    app = VotacionApp(root)
    root.mainloop()
