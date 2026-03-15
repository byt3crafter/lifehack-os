"""Projects view - manage projects and milestones."""
import customtkinter as ctk
from datetime import datetime
from typing import TYPE_CHECKING

from ..theme import COLORS, FONTS, create_card_frame, create_button, create_entry
from ..components import ProgressBar

if TYPE_CHECKING:
    from ..app import LifeHackApp


class ProjectsView(ctk.CTkFrame):
    """View for managing projects."""
    
    def __init__(self, parent, app: 'LifeHackApp'):
        super().__init__(parent, fg_color=COLORS['bg_primary'])
        self.app = app
        self._build_ui()
        self.refresh()
    
    def _build_ui(self):
        # Header
        header = ctk.CTkFrame(self, fg_color='transparent')
        header.pack(fill='x', padx=24, pady=(24, 16))
        
        ctk.CTkLabel(
            header, text="Projects",
            font=FONTS['h1'], text_color=COLORS['text_primary']
        ).pack(side='left')
        
        create_button(
            header, "+ New Project",
            command=self._show_add_dialog
        ).pack(side='right')
        
        # Projects list
        self.projects_frame = ctk.CTkScrollableFrame(
            self,
            fg_color='transparent'
        )
        self.projects_frame.pack(fill='both', expand=True, padx=24, pady=(0, 24))
    
    def refresh(self):
        """Refresh the projects list."""
        for widget in self.projects_frame.winfo_children():
            widget.destroy()
        
        projects = self.app.project_repo.get_all(include_completed=False)
        
        if not projects:
            ctk.CTkLabel(
                self.projects_frame,
                text="No active projects. Start one!",
                font=FONTS['body'],
                text_color=COLORS['text_muted']
            ).pack(pady=40)
            return
        
        for project in projects:
            card = ProjectCard(
                self.projects_frame,
                project,
                self.app,
                on_refresh=self.refresh
            )
            card.pack(fill='x', pady=8)
    
    def _show_add_dialog(self):
        dialog = AddProjectDialog(self, self.app)
        dialog.grab_set()


class ProjectCard(ctk.CTkFrame):
    """Card displaying a project with milestones."""
    
    def __init__(self, parent, project, app, on_refresh=None):
        super().__init__(
            parent,
            fg_color=COLORS['bg_card'],
            corner_radius=8,
            border_width=1,
            border_color=COLORS['border']
        )
        
        self.project = project
        self.app = app
        self.on_refresh = on_refresh
        
        self._build_ui()
    
    def _build_ui(self):
        # Header
        header = ctk.CTkFrame(self, fg_color='transparent')
        header.pack(fill='x', padx=16, pady=(16, 8))
        
        ctk.CTkLabel(
            header, text=self.project.name,
            font=FONTS['h3'], text_color=COLORS['text_primary']
        ).pack(side='left')
        
        status_colors = {
            'active': COLORS['success'],
            'paused': COLORS['warning'],
            'complete': COLORS['accent']
        }
        
        ctk.CTkLabel(
            header, text=self.project.status.value.upper(),
            font=FONTS['small'],
            text_color=status_colors.get(self.project.status.value, COLORS['text_muted'])
        ).pack(side='right')
        
        # Description
        if self.project.description:
            ctk.CTkLabel(
                self, text=self.project.description,
                font=FONTS['body'],
                text_color=COLORS['text_secondary'],
                wraplength=500
            ).pack(anchor='w', padx=16, pady=(0, 8))
        
        # Progress
        ProgressBar(
            self,
            value=self.project.progress,
            label="Progress",
            color=COLORS['accent']
        ).pack(fill='x', padx=16, pady=(0, 12))
        
        # Milestones
        if self.project.milestones:
            ctk.CTkLabel(
                self, text="Milestones",
                font=FONTS['body_bold'],
                text_color=COLORS['text_secondary']
            ).pack(anchor='w', padx=16, pady=(0, 4))
            
            for milestone in self.project.milestones:
                self._add_milestone_row(milestone)
        
        # Add milestone button
        btn_frame = ctk.CTkFrame(self, fg_color='transparent')
        btn_frame.pack(fill='x', padx=16, pady=(8, 16))
        
        create_button(
            btn_frame, "+ Add Milestone",
            command=self._add_milestone,
            variant='ghost',
            height=28
        ).pack(side='left')
        
        if self.project.status.value == 'active':
            create_button(
                btn_frame, "Complete Project ✓",
                command=self._complete_project,
                variant='success',
                height=28
            ).pack(side='right')
    
    def _add_milestone_row(self, milestone):
        row = ctk.CTkFrame(self, fg_color=COLORS['bg_secondary'], corner_radius=4)
        row.pack(fill='x', padx=16, pady=2)
        
        checkbox = ctk.CTkCheckBox(
            row,
            text=milestone.name,
            font=FONTS['body'],
            checkbox_height=20,
            checkbox_width=20,
            fg_color=COLORS['success'] if milestone.is_complete else COLORS['bg_card'],
            command=lambda m=milestone: self._toggle_milestone(m)
        )
        checkbox.pack(side='left', padx=8, pady=6)
        
        if milestone.is_complete:
            checkbox.select()
        
        ctk.CTkLabel(
            row, text=f"+{milestone.points}",
            font=FONTS['small'],
            text_color=COLORS['xp_gold']
        ).pack(side='right', padx=8)
    
    def _toggle_milestone(self, milestone):
        if not milestone.is_complete:
            self.app.project_repo.complete_milestone(milestone.id)
            self.app.stats_repo.add_points(
                'milestone', milestone.points,
                f"Milestone: {milestone.name}",
                milestone.id
            )
            if self.on_refresh:
                self.on_refresh()
    
    def _add_milestone(self):
        dialog = AddMilestoneDialog(self, self.app, self.project.id, self.on_refresh)
        dialog.grab_set()
    
    def _complete_project(self):
        from ...domain.entities import ProjectStatus
        
        self.project.status = ProjectStatus.COMPLETE
        self.project.completed_at = datetime.now()
        self.app.project_repo.update(self.project)
        
        self.app.stats_repo.add_points(
            'project', self.project.points_complete,
            f"Completed project: {self.project.name}",
            self.project.id
        )
        
        if self.on_refresh:
            self.on_refresh()


class AddProjectDialog(ctk.CTkToplevel):
    """Dialog for adding a new project."""
    
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.parent_view = parent
        
        self.title("New Project")
        self.geometry("450x350")
        self.configure(fg_color=COLORS['bg_primary'])
        self.transient(parent)
        
        self._build_ui()
    
    def _build_ui(self):
        ctk.CTkLabel(
            self, text="New Project",
            font=FONTS['h2'], text_color=COLORS['text_primary']
        ).pack(pady=(24, 16))
        
        form = ctk.CTkFrame(self, fg_color='transparent')
        form.pack(fill='x', padx=24)
        
        # Name
        ctk.CTkLabel(
            form, text="Name",
            font=FONTS['body'], text_color=COLORS['text_secondary']
        ).pack(anchor='w')
        self.name_entry = create_entry(form, "e.g., Launch RunState website")
        self.name_entry.pack(fill='x', pady=(4, 12))
        
        # Description
        ctk.CTkLabel(
            form, text="Description (optional)",
            font=FONTS['body'], text_color=COLORS['text_secondary']
        ).pack(anchor='w')
        self.desc_entry = ctk.CTkTextbox(
            form,
            height=80,
            fg_color=COLORS['bg_secondary'],
            corner_radius=6
        )
        self.desc_entry.pack(fill='x', pady=(4, 16))
        
        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color='transparent')
        btn_frame.pack(fill='x', padx=24, pady=24)
        
        create_button(
            btn_frame, "Cancel",
            command=self.destroy,
            variant='ghost'
        ).pack(side='left')
        
        create_button(
            btn_frame, "Create Project",
            command=self._save
        ).pack(side='right')
    
    def _save(self):
        from ...domain.entities import Project
        
        name = self.name_entry.get().strip()
        if not name:
            return
        
        project = Project(
            name=name,
            description=self.desc_entry.get("1.0", "end-1c").strip()
        )
        
        project = self.app.project_repo.create(project)
        
        # Award points for starting
        self.app.stats_repo.add_points(
            'project', project.points_start,
            f"Started project: {project.name}",
            project.id
        )
        
        self.destroy()
        self.parent_view.refresh()


class AddMilestoneDialog(ctk.CTkToplevel):
    """Dialog for adding a milestone."""
    
    def __init__(self, parent, app, project_id, on_refresh):
        super().__init__(parent)
        self.app = app
        self.project_id = project_id
        self.on_refresh = on_refresh
        
        self.title("Add Milestone")
        self.geometry("400x250")
        self.configure(fg_color=COLORS['bg_primary'])
        self.transient(parent)
        
        self._build_ui()
    
    def _build_ui(self):
        ctk.CTkLabel(
            self, text="New Milestone",
            font=FONTS['h2'], text_color=COLORS['text_primary']
        ).pack(pady=(24, 16))
        
        form = ctk.CTkFrame(self, fg_color='transparent')
        form.pack(fill='x', padx=24)
        
        ctk.CTkLabel(
            form, text="Name",
            font=FONTS['body'], text_color=COLORS['text_secondary']
        ).pack(anchor='w')
        self.name_entry = create_entry(form, "e.g., Complete MVP")
        self.name_entry.pack(fill='x', pady=(4, 12))
        
        ctk.CTkLabel(
            form, text="Points",
            font=FONTS['body'], text_color=COLORS['text_secondary']
        ).pack(anchor='w')
        self.points_entry = create_entry(form, "50")
        self.points_entry.pack(fill='x', pady=(4, 16))
        
        btn_frame = ctk.CTkFrame(self, fg_color='transparent')
        btn_frame.pack(fill='x', padx=24, pady=24)
        
        create_button(
            btn_frame, "Cancel",
            command=self.destroy,
            variant='ghost'
        ).pack(side='left')
        
        create_button(
            btn_frame, "Add",
            command=self._save
        ).pack(side='right')
    
    def _save(self):
        from ...domain.entities import Milestone
        
        name = self.name_entry.get().strip()
        if not name:
            return
        
        try:
            points = int(self.points_entry.get())
        except ValueError:
            points = 50
        
        milestone = Milestone(
            project_id=self.project_id,
            name=name,
            points=points
        )
        
        self.app.project_repo.add_milestone(milestone)
        self.destroy()
        
        if self.on_refresh:
            self.on_refresh()
