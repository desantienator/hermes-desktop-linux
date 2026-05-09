from __future__ import annotations
import shutil, subprocess, sys
try:
    import tkinter as tk
    from tkinter import ttk, messagebox, simpledialog
except ModuleNotFoundError as exc:
    print("Hermes Desktop Linux needs Tkinter. Install it with: sudo apt install python3-tk", file=sys.stderr)
    raise SystemExit(2) from exc
from .models import ConnectionProfile, ProfileStore
from .remote import SSHClient

SECTIONS = ["Overview", "Sessions", "Kanban", "Files", "Usage", "Skills", "Cron", "Terminal"]

class HermesLinuxApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Hermes Desktop Linux")
        self.geometry("1180x760")
        self.minsize(900, 560)
        self.store = ProfileStore()
        self.profiles = self.store.load()
        self.profile = self.profiles[0]
        self.client = SSHClient(self.profile)
        self.current_file = ""
        self._build_ui()
        self.show_section("Overview")

    def _build_ui(self):
        self.columnconfigure(1, weight=1); self.rowconfigure(1, weight=1)
        top = ttk.Frame(self, padding=8); top.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Label(top, text="Hermes Desktop Linux", font=("TkDefaultFont", 14, "bold")).pack(side="left")
        self.profile_var = tk.StringVar(value=self.profile.name)
        self.profile_combo = ttk.Combobox(top, textvariable=self.profile_var, values=[p.name for p in self.profiles], width=24, state="readonly")
        self.profile_combo.pack(side="right", padx=4); self.profile_combo.bind("<<ComboboxSelected>>", self.switch_profile)
        ttk.Button(top, text="Edit profile", command=self.edit_profile).pack(side="right", padx=4)
        ttk.Button(top, text="Refresh", command=self.refresh).pack(side="right", padx=4)

        nav = ttk.Frame(self, padding=(8, 4)); nav.grid(row=1, column=0, sticky="ns")
        self.nav_buttons = {}
        for s in SECTIONS:
            b = ttk.Button(nav, text=s, command=lambda x=s: self.show_section(x)); b.pack(fill="x", pady=2)
            self.nav_buttons[s]=b

        self.main = ttk.Frame(self, padding=8); self.main.grid(row=1, column=1, sticky="nsew")
        self.main.rowconfigure(1, weight=1); self.main.columnconfigure(0, weight=1)
        self.title_label = ttk.Label(self.main, text="", font=("TkDefaultFont", 13, "bold")); self.title_label.grid(row=0,column=0,sticky="w")
        self.body = ttk.Frame(self.main); self.body.grid(row=1,column=0,sticky="nsew", pady=(8,0))
        self.status = tk.StringVar(value="Ready")
        ttk.Label(self, textvariable=self.status, anchor="w", padding=6).grid(row=2,column=0,columnspan=2,sticky="ew")

    def clear(self):
        for w in self.body.winfo_children(): w.destroy()
        self.body.rowconfigure(0, weight=1); self.body.columnconfigure(0, weight=1)

    def show_section(self, section):
        self.section = section; self.title_label.config(text=section); self.clear()
        getattr(self, f"section_{section.lower()}")()

    def refresh(self): self.show_section(getattr(self, 'section', 'Overview'))

    def run(self, action, arg="", payload=None, timeout=60):
        self.status.set(f"Running {action} on {self.profile.target}…"); self.update_idletasks()
        res = self.client.run_action(action, arg, payload, timeout)
        self.status.set(("OK" if res.ok else "Failed") + f" in {res.elapsed_ms}ms")
        if not res.ok: messagebox.showerror("Remote action failed", res.error[:4000])
        return res

    def switch_profile(self, _=None):
        name = self.profile_var.get(); self.profile = next(p for p in self.profiles if p.name == name)
        self.client = SSHClient(self.profile); self.refresh()

    def edit_profile(self):
        p = self.profile
        text = simpledialog.askstring("Profile", "name,host,user,port,hermes_home,ssh_alias", initialvalue=f"{p.name},{p.host},{p.user},{p.port},{p.hermes_home},{p.ssh_alias}")
        if not text: return
        parts = [x.strip() for x in text.split(',', 5)] + [""]*6
        np = ConnectionProfile(parts[0], parts[1], parts[2], int(parts[3] or 22), parts[4] or "~/.hermes", parts[5])
        self.profiles = [x for x in self.profiles if x.name != p.name] + [np]
        self.store.save(self.profiles); self.profile=np; self.client=SSHClient(np)
        self.profile_combo.config(values=[x.name for x in self.profiles]); self.profile_var.set(np.name); self.refresh()

    def tree_json(self, data):
        txt = tk.Text(self.body, wrap="none", bg="#11151c", fg="#d7dde8", insertbackground="#d7dde8")
        txt.grid(row=0,column=0,sticky="nsew")
        import json; txt.insert("1.0", json.dumps(data, indent=2, default=str)); txt.config(state="disabled")

    def section_overview(self):
        r=self.run('overview'); self.tree_json(r.data if r.ok else {})

    def section_usage(self):
        r=self.run('usage'); self.tree_json(r.data if r.ok else {})

    def section_cron(self):
        r=self.run('cron'); self.tree_json(r.data if r.ok else {})

    def section_kanban(self):
        r=self.run('kanban'); self.tree_json(r.data if r.ok else {})

    def section_sessions(self):
        self.list_and_preview('sessions')

    def section_skills(self):
        self.list_and_preview('skills')

    def section_files(self):
        bar=ttk.Frame(self.body); bar.grid(row=0,column=0,sticky='ew')
        path=tk.StringVar(value=self.profile.hermes_home)
        ttk.Entry(bar,textvariable=path).pack(side='left',fill='x',expand=True)
        ttk.Button(bar,text='Open',command=lambda:self.populate_files(path.get())).pack(side='left')
        pane=ttk.PanedWindow(self.body, orient='horizontal'); pane.grid(row=1,column=0,sticky='nsew'); self.body.rowconfigure(1,weight=1)
        self.file_tree=ttk.Treeview(pane, columns=('path','size'), show='headings'); self.file_tree.heading('path',text='Path'); self.file_tree.heading('size',text='Size')
        edit_frame=ttk.Frame(pane); edit_frame.rowconfigure(0,weight=1); edit_frame.columnconfigure(0,weight=1)
        self.editor=tk.Text(edit_frame, wrap='none'); self.editor.grid(row=0,column=0,sticky='nsew')
        ttk.Button(edit_frame,text='Save',command=self.save_current_file).grid(row=1,column=0,sticky='e')
        pane.add(self.file_tree, weight=1); pane.add(edit_frame, weight=2)
        self.file_tree.bind('<Double-1>', lambda e:self.open_selected_file())
        self.populate_files(path.get())

    def populate_files(self, path):
        r=self.run('files', path)
        self.file_tree.delete(*self.file_tree.get_children())
        if r.ok:
            for item in r.data:
                self.file_tree.insert('', 'end', values=(('[DIR] ' if item['is_dir'] else '')+item['path'], item['size']))

    def open_selected_file(self):
        vals=self.file_tree.item(self.file_tree.focus(),'values')
        if not vals: return
        path=vals[0].replace('[DIR] ','')
        if vals[0].startswith('[DIR] '): self.populate_files(path); return
        r=self.run('read', path)
        if r.ok:
            self.current_file=path; self.editor.delete('1.0','end'); self.editor.insert('1.0', r.data.get('content') or '')

    def save_current_file(self):
        if not self.current_file: return
        if messagebox.askyesno('Save remote file?', self.current_file):
            self.run('write', self.current_file, {'content': self.editor.get('1.0','end-1c')})

    def list_and_preview(self, action):
        pane=ttk.PanedWindow(self.body, orient='horizontal'); pane.grid(row=0,column=0,sticky='nsew')
        tree=ttk.Treeview(pane, columns=('name','path','meta'), show='headings'); tree.heading('name',text='Name'); tree.heading('path',text='Path'); tree.heading('meta',text='Meta')
        txt=tk.Text(pane, wrap='word', bg='#11151c', fg='#d7dde8')
        pane.add(tree, weight=1); pane.add(txt, weight=2)
        r=self.run(action)
        if r.ok:
            for item in r.data:
                tree.insert('', 'end', values=(item.get('name',''), item.get('path',''), item.get('description') or item.get('size','')))
        def open_item(_):
            vals=tree.item(tree.focus(),'values')
            if not vals: return
            rr=self.run('read', vals[1]); txt.delete('1.0','end'); txt.insert('1.0', (rr.data or {}).get('content') or '')
        tree.bind('<Double-1>', open_item)

    def section_terminal(self):
        msg = ttk.Label(self.body, text="Open an SSH terminal to the active Hermes host. Embedded terminal is the one cursed subsystem left for v0.2.")
        msg.grid(row=0,column=0,sticky='w',pady=8)
        ttk.Button(self.body, text=f"Open terminal: {self.profile.target}", command=self.open_terminal).grid(row=1,column=0,sticky='w')

    def open_terminal(self):
        terms=[['x-terminal-emulator','-e'],['gnome-terminal','--'],['konsole','-e'],['xfce4-terminal','-e'],['xterm','-e'],['kitty']]
        sshcmd = ['bash','-lc', f"ssh -p {self.profile.port} {self.profile.target}" if self.profile.host not in ('localhost','127.0.0.1') or self.profile.ssh_alias else 'bash']
        for t in terms:
            if shutil.which(t[0]):
                subprocess.Popen(t + sshcmd); return
        messagebox.showinfo('No terminal emulator found', 'Install x-terminal-emulator, gnome-terminal, konsole, xterm, kitty, or run SSH manually.')

def main():
    app = HermesLinuxApp(); app.mainloop()

if __name__ == "__main__": main()
