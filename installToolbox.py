import asyncio
import json
import os.path
import inspect
import re
import shutil
import traceback
import urllib.request

from PySide6.QtCore import Qt
from PySide6.QtWidgets import *
from PySide6.QtGui import QIcon
from maya import cmds
from maya import mel
from maya.OpenMayaUI import MQtUtil
from maya.app.general.mayaMixin import MayaQWidgetBaseMixin
from shiboken6 import wrapInstance
import urllib.request as request
from typing import Optional

__version__ = '1.0.0'

# Core constant's
_REPO = 'https://raw.githubusercontent.com/SwissCirkus/Toolbox/Installer-v2/'
_NETWORK_ROOT = '\\\\bigtop/bigtop'
W_OBJ = 'cirkusinstallerwindow'
W_TITLE = 'Cirkus Toolbox Installer'
DEFAULT_PATH = 'Server (default)'


def _maya_main_window():
    """
    Returns an instance of the main window for maya.
    """
    return wrapInstance(int(MQtUtil.mainWindow()), QMainWindow)


def _maya_delete_ui(window_title, window_object):
    """
    Clean up and delete matching windows.
    """
    if cmds.window(window_object, q=True, exists=True):
        cmds.deleteUI(window_object)
    if cmds.dockControl(f'MayaWindow|{window_title}', q=True, exists=True):
        cmds.deleteUI(f'MayaWindow|{window_title}')


def _maya_delete_workspace(window_object):
    """
    Clean up any matchign workspace controls
    """
    control = f'{window_object}WorkspaceControl'
    if cmds.workspaceControl(control, q=True, exists=True):
        cmds.workspaceControl(control, e=True, close=True)
        cmds.deleteUI(control, control=True)


def download_data(url: str, local: str = None) -> Optional[str]:
    """
    Downloads data from an url. If local is not defined or set to None
    then it this will return the data in a string format otherwise
    it will be written to file.

    :url:    URL to where the data is being downloaded from.

    :local:  Full path to the local file the data will be written into.
             if this is empty then it will be returned,
    """
    data = None
    to_file = local is not None

    if to_file and not os.path.exists(os.path.dirname(local)):
        os.makedirs(os.path.dirname(local))

    def write_file(r, f):
        while True:
            block = r.read(8129)
            if not block:
                break
            f.write(block)

    def write_data(r):
        nonlocal data
        if data is None:
            data = ''
        while True:
            block = r.read(8129)
            if not block:
                break
            data += block.decode('utf-8')

    with request.urlopen(url) as req:
        if to_file:
            with open(local, 'wb') as file:
                write_file(req, file)
        else:
            write_data(req)

    return data


def _clean_up():
    """Cleans up all instances of the installation window from maya."""
    _maya_delete_ui(W_TITLE, W_OBJ)
    _maya_delete_workspace(W_OBJ)


def create_shelf(name):
    """Creates a new shelf if it does not already exist"""
    exists = name in cmds.layout('ShelfLayout', q=True, ca=True)
    if not exists:
        print(f'Creating new shelf {name} to install the tools into.')
        mel.eval(f'addNewShelfTab("{name}")')


def _create_shelf_popups(parent: str, click_type: str, menus: list):
    """
    Adds all the configured popup menu items to a shelf button.
    """
    # Create a new left click menu and add the menu items
    # to that popup.
    if 'left' in click_type:
        popup = cmds.popupMenu(button=1, p=parent)
        for item in menus:
            cmds.menuItem(
                l=item.get('label', 'Unlabeled Item'),
                d=item.get('divider', False),
                command=item.get('command', ''),
                p=popup
            )
        return

    # Add items to the shelf button in the right
    # click menu.
    for item in menus:
        cmds.shelfButton(
            parent, e=True,
            mi=(item['label'], item['command'])
        )


def create_shelf_button(parent: str, btn_data: dict):
    """
    Creates a new shelf button from the given data.
    """
    label = btn_data.get('label', 'Undefined Button')
    icon = btn_data.get('icon', 'commandButton.png')
    cmd = btn_data.get('command', '')
    stp = btn_data.get('stp', 'mel')
    sbm = btn_data.get('sbm', '')

    if icon == 'separator':
        # Make it a seperator if it is one
        cmds.separator(p=parent, style='shelf', horizontal=0)
        return

    if isinstance(icon, list):
        icon = icon[0]

    # Make the button here
    shelf_btn = cmds.shelfButton(
        p=parent,
        w=32, h=32,
        label=label,
        image1=icon,
        command=cmd,
        commandRepeatable=True,
        sourceType=stp,
        statusBarMessage=sbm
    )

    # If button has a menu item create it
    if 'menuItem' in btn_data:
        click_type = btn_data.get('menuItem-click-type', 'right').lower()
        _create_shelf_popups(shelf_btn, click_type, btn_data.get('menuItem', []))


def remove_shelf_button(shelf, button):
    """
    Deletes a button or all seperators from a shelf. If the button name
    is 'seperaror' then all seperators will be removed from the shelf.
    If 'ALL' is defined then all buttons will be deleted.
    """
    buttons = cmds.shelfLayout(shelf, q=True, childArray=True)
    if buttons is None:
        return

    # Sets if this is operating in seperaror or button mode
    seperator = button == 'separator'
    ALL = button == 'ALL'

    for btn in buttons:
        if ALL:
            cmds.deleteUI(btn)
            continue
        if seperator:
            if cmds.objectTypeUI(btn, isType='separator'):
                cmds.deleteUI(btn)
        elif button == btn:
            cmds.deleteUI(btn)


class RowColumnWidget(QWidget):
    """Simple widget to build a set of rows and columns"""

    def __init__(self, columns: int = 2):
        super(RowColumnWidget, self).__init__()

        # Have a min value of 1
        if columns < 1:
            columns = 1

        self.columns = columns
        self._widgets = []
        self._columns = []

        self._layout = QHBoxLayout()
        self.setLayout(self._layout)

        for i in range(columns):
            layout_base = QVBoxLayout()
            layout = QVBoxLayout()
            layout_base.addLayout(layout)
            layout_base.addStretch()
            self._layout.addLayout(layout_base)
            self._columns.append(layout)

        self.adjustSize()

    def list(self):
        return self._widgets

    def addWidget(self, widget: QWidget):
        self._widgets.append(widget)
        col = self.columns - 1 - len(self._widgets) % self.columns
        self._columns[col].addWidget(widget)

    def reset(self):
        widget: QWidget
        for widget in self._widgets:
            widget.deleteLater()
            widget.setParent(None)
        self._widgets.clear()


class ToolButtonWidget(QPushButton):

    def __init__(self, *args, **kwargs):
        super(ToolButtonWidget, self).__init__(*args, **kwargs)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setCheckable(True)

        self.setStyleSheet('''
        ToolButtonWidget {
            background: transparent;
            border: 3px solid #5D5D5D;
            padding-top: 7px;
            padding-bottom: 7px;
            border-radius: 8px;
        }
        ToolButtonWidget:checked {
            border-color: #709B64;
        }
        ''')


class Installer:
    """Simple Installer class to handle installing the tools."""

    def __init__(self, shelf, tool_data, to_install, install_from: dict,
                 scripts_path, icons_path, progress_bar, status_widget):
        self.shelf = shelf
        self._step = 0
        self.tool_data = tool_data
        self.to_install = to_install
        self.scripts_path = scripts_path
        self.icons_path = icons_path
        self.progress_bar: QProgressBar = progress_bar
        self.status_widget: QLabel = status_widget

        self.scripts = []
        self.modules = []
        self.icons = []

        # Define if the icons or scripts should be installed into a
        # locally defined dir.
        self.install_scripts = scripts_path != DEFAULT_PATH
        self.install_icons = icons_path != DEFAULT_PATH

        self.src_path: str = install_from['path']
        self.is_local: bool = install_from['is_local']

        self._file_pattern = re.compile('[\\w.]+\\.\\w+$')

        # Value ranges from 0 to 100
        self.install_progress = 0
        self.install_steps = 0

    def update_progresss_bar(self):
        progress = self.install_progress / self.install_steps
        self.progress_bar.setValue(progress * 100)

    def index_files(self, data: dict):
        """
        Looks at a diconary to find any scripts or icons that will need
        to be installed.
        """
        if data is None:
            return

        def append(name: str, _plural=False) -> list:
            # Return the data as a list from the given name if it exists.
            nonlocal data
            nonlocal self
            ls = []
            if name in data:
                if isinstance(data[name], list):
                    ls += data[name]
                else:
                    ls.append(data[name])
            if not _plural:
                ls += append(f'{name}s', True)
            # Filter out anything that's not a file and then return result
            return list(filter(lambda file: self._file_pattern.search(file), ls))

        # All paths to look for and index
        if self.install_scripts:
            self.scripts += append('script')
            self.modules += append('module')
        self.icons += append('icon')

        if 'buttons' in data and isinstance(data['buttons'], list):
            for btn in data['buttons']:
                self.index_files(btn)

        # Deep indexing
        for index in data:
            if isinstance(data[index], dict):
                self.index_files(data[index])
                continue

    def _async_copy(self, files, to, extra: str = '') -> list:
        tasks = []

        async def cop(src, dst):
            nonlocal self
            print(f'Copying {self._file_pattern.search(src)[0]} -> <{dst}>')

            # Make directory if needed
            if not os.path.exists(os.path.dirname(dst)):
                os.makedirs(os.path.dirname(dst))

            # Copy filre to new dest
            shutil.copy(src, dst)

            # Update progress bar
            self.install_progress += 1
            self.update_progresss_bar()

        for file in files:
            tasks.append(asyncio.create_task(cop(f'{self.src_path}/{extra}{file}', f'{to}/{file}')))
        return tasks

    def _async_download(self, files, to, extra: str = '') -> list:
        tasks = []

        async def cop(src, dst):
            nonlocal self
            print(f'Downloading {self._file_pattern.search(src)[0]} -> <{dst}>')
            download_data(src, dst)
            self.install_progress += 1
            self.update_progresss_bar()

        for file in files:
            tasks.append(asyncio.create_task(cop(f'{_REPO}{extra}{file}', f'{to}/{file}')))
        return tasks

    async def _install_files(self, files, to, extra: str = ''):
        """
        Downloads/Copies all files for the selected tools into the respectivly
        selected install directory.
        """
        tasks: list
        if self.is_local:
            tasks = self._async_copy(files, to, extra)
        else:
            tasks = self._async_download(files, to, extra)
        await asyncio.gather(*tasks)
        # self._async_download(files, to)
        self.update_progresss_bar()

    def _install_buttons(self):
        """Installs all the buttons to the shelf."""
        def index_buttons(t):
            nonlocal self
            for btn in t['buttons']:
                create_shelf_button(self.shelf, btn)

        for index in self.tool_data:
            if index not in self.to_install:
                continue
            tool = self.tool_data[index]
            if 'buttons' in tool:
                index_buttons(tool)

    def start(self):
        """Start installing all selected tools"""
        # Index all the files that need to be installed
        for tool in self.tool_data:
            if tool in self.to_install:
                self.index_files(self.tool_data[tool])

        files: int = 0
        if self.install_icons:
            files += len(self.icons)
        if self.install_scripts:
            files += len(self.scripts) + len(self.modules)
        self.install_steps = files

        if self.install_icons:
            self.status_widget.setText('Downloading icons')
            asyncio.run(
                self._install_files(self.icons, self.icons_path, 'icons/')
            )
        if self.install_scripts:
            self.status_widget.setText('Downloading scripts')
            asyncio.run(
                self._install_files(self.scripts, self.scripts_path)
            )
            self.status_widget.setText('Downloading modules')
            asyncio.run(
                self._install_files(self.modules, self.scripts_path)
            )

        self.status_widget.setText('Creating shelf buttons')
        self._install_buttons()


class InstallerWindow(MayaQWidgetBaseMixin, QDialog):

    def __init__(self):
        _clean_up()
        super(InstallerWindow, self).__init__(_maya_main_window())

        # Setup base window properties
        self.setObjectName(W_OBJ)
        self.setWindowTitle(W_TITLE)
        self.setWindowFlags(Qt.Window)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        # self.setFixedWidth(400)
        # self.setMaximumWidth(700)

        # Define base vars
        self._local_toolbox_dir: Optional[str] = None  # local install dir
        self._toolbox_data: Optional[dict] = None  # all data from toolboxShelf.json
        self._tools_list_widget = RowColumnWidget(2)
        self._remote_data: Optional[dict] = None
        self._tools_install_status = {}
        self._tasks = []

        # Build the UI
        self._build_ui()
        self._check_install_state()
        self._find_local_install()

    def _find_local_install(self):
        """
        Attempt to find the local install directory for the toolbox and prefill
        the input. If the nothing can be found then the input will remain empty.
        """
        # Candidate roots to check, in order. _NETWORK_ROOT is a hardcoded UNC
        # path that only resolves on machines with direct \\bigtop\bigtop access.
        # DEPLOY_PATH is the same env var Maya.env already uses for
        # MAYA_SCRIPT_PATH/PYTHONPATH/XBMLANGPATH, so it works regardless of how
        # the network share happens to be mapped (drive letter, Dropbox path, etc).
        candidates = [f'{_NETWORK_ROOT}/Job_3/System/Deployment/Toolbox']
        deploy_path = os.getenv('DEPLOY_PATH')
        if deploy_path:
            candidates.append(os.path.join(deploy_path, 'Toolbox'))

        toolbox_shelf_file = 'toolboxShelf.json'

        for path in candidates:
            if not os.path.exists(path):
                continue
            if toolbox_shelf_file not in os.listdir(path):
                cmds.warning(f'Missing toolboxShelf.json from {path}')
                continue

            # Set network updates to be done locally by default. This is
            # only set as a default as it's likely these files be up-to-date and
            # be much faster to update from then downloading.
            self._install_local_text.setText(path)
            self._local_toolbox_dir = path;
            self._install_from_options.setCurrentIndex(1)
            self._fetch_tools_data()
            return

        # Set text to empty if not on a network drive
        self._install_local_text.setText('')




    @property
    def is_local_install(self) -> bool:
        return self._install_from_options.currentIndex()

    def _check_install_state(self):
        """
        Sets the state of the install button to be enabled or disabled
        depending on if all parameters are valid. This will also update
        the listed tools in the UI to match if it is sourcing from either
        remote or local paths.
        """
        self._fetch_tools_data()
        if self.is_local_install:
            if self._local_toolbox_dir is None:
                self.install_btn.setEnabled(False)
                self._load_tools(None)
                return
            # _fetch_tools_data() already loaded the local toolboxShelf.json.
            # Don't clobber it with remote data below.
            self.install_btn.setEnabled(True)
            return
        self._load_tools(self._remote_data)
        self.install_btn.setEnabled(True)

    def _select_install_dir(self):
        """
        Opens a dialog to select the directory where the Cirkus Toolbox tools are located.
        If the directory does not have the required files to install the tools from then
        a warning will be shown and not be set.
        """
        default_dir = os.getcwd()
        if self._install_local_text.text() != '':
            default_dir = self._install_local_text.text()

        # Built as an explicit instance (rather than the static
        # getExistingDirectory convenience call) so it can be forced to the
        # front - dialogs spawned from a MayaQWidgetBaseMixin window can
        # otherwise open behind the main Maya window with no visible sign
        # they opened at all.
        dialog = QFileDialog(self, 'Select install directory', default_dir)
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        dialog.setWindowModality(Qt.ApplicationModal)
        dialog.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        dialog.raise_()
        dialog.activateWindow()

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        selected = dialog.selectedFiles()
        if not selected:
            return
        responce = selected[0]

        # ignore cancels
        if responce is None or len(responce) == 0:
            return

        # Check if the required files are in the directory to install with
        files = os.listdir(responce)
        if 'toolboxShelf.json' not in files:
            cmds.warning('Invalid Install Directory. This does not contain the required data to install the Cirkus '
                         'Toolbox with.')
            self._check_install_state()
            self._load_tools(None)
            return

        # Update internal vars and UI
        self._local_toolbox_dir = responce
        self._install_local_text.setText(responce)
        self._check_install_state()
        self._fetch_tools_data()

    def _ui_install_build(self) -> QLayout:
        """
        Builds UI elements to handle the options of switching between a remote
        or local installation.
        """
        layout = QFormLayout()
        layout.setContentsMargins(30, 30, 30, 0)
        layout.setHorizontalSpacing(30)

        content_layout = QHBoxLayout()

        # Install Type
        self._install_from_options = QComboBox()
        self._install_from_options.addItems(['Remote Install', 'Local Install'])

        local_layout = QHBoxLayout()
        local_widget = QWidget(layout=local_layout, visible=self._install_from_options.currentIndex())
        open_search_btn = QPushButton(icon=QIcon(':/folder-open.png'))
        # Fall back to a text label if the ':/folder-open.png' Qt resource isn't
        # registered in this build - otherwise the button can render with no
        # icon and effectively no visible/clickable hit area.
        if open_search_btn.icon().isNull():
            open_search_btn.setText('...')
        open_search_btn.setMinimumWidth(30)
        self._install_local_text = QLineEdit(disabled=True)
        local_layout.addWidget(self._install_local_text)
        local_layout.addWidget(open_search_btn)

        local_layout.setContentsMargins(0, 0, 0, 0)

        content_layout.addWidget(self._install_from_options)
        content_layout.addWidget(local_widget)

        layout.addRow(QLabel('Install From'), content_layout)
        # layout.addRow(QLabel(''), local_widget)

        # Make Connections
        self._install_from_options.currentIndexChanged.connect(lambda x: (
            local_widget.setVisible(x), self._check_install_state()
        ))
        open_search_btn.clicked.connect(lambda x: self._select_install_dir())

        return layout

    def _ui_install_progress_splash(self) -> QWidget:
        """Creates the UI for the installing splash screen."""
        layout = QVBoxLayout()
        widget = QWidget(layout=layout)

        layout.addStretch()
        layout.addWidget(QLabel('<h1>Cirkus Toolbox</h1>', alignment=Qt.AlignHCenter))
        self._install_status = QLabel('Installing...', alignment=Qt.AlignHCenter)
        layout.addWidget(self._install_status)

        self._progress_widget = QProgressBar()
        self._progress_widget.setValue(0)

        widget.setStyleSheet('''
        QProgressBar {
            border: 0;
            border-radius: 8px;
            text-align: center;
            height: 40px;
        }
        QProgressBar:chunk {
            border-radius: 8px;
            background: #709B64;
        }
        QProgressBar[error="true"]:chunk {background: #DC564C;}
        ''')

        layout.addWidget(self._progress_widget)
        layout.addStretch()

        return widget

    def _build_ui(self):
        """
        Builds the UI for the installer window.
        """
        layout = QVBoxLayout()

        # Some simple styling
        self.setStyleSheet('''
        QComboBox { padding: 5px 10px; } 
        #install-btn { background: #709B64; border-radius: 8px; }
        #install-btn:hover { background: #97C989; }
        #install-btn:pressed { background: #3F5838; }
        #install-btn:disabled { background: #5E7059; }
        #cancel-btn { background: #5D5D5D; border-radius: 8px; }
        #cancel-btn:hover { background: #787878; }
        #cancel-btn:pressed { background: #2B2B2B; }
        ''')

        # Install options
        options_layout = QFormLayout()
        options_layout.setContentsMargins(30, 0, 30, 30)
        options_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        options_layout.setHorizontalSpacing(30)

        # Install Type
        self.scripts_install_loc = QComboBox()
        self.scripts_install_loc.setStatusTip(
            'Set where all scripts are installed. Default\'s to not installing any for pre installed scripts.'
            )
        self.icons_install_loc = QComboBox()
        self.icons_install_loc.setStatusTip(
            'Set where icons are installed. Default\'s to not installing any for pre installed icons.'
            )
        self.shelf_name = QLineEdit(placeholderText='CoolTool')

        self.scripts_install_loc.addItem(DEFAULT_PATH)
        self.icons_install_loc.addItem(DEFAULT_PATH)

        # options_layout.addRow(QLabel('Install From'), self._install_from_options)
        options_layout.addRow(QLabel('Scripts Path'), self.scripts_install_loc)
        options_layout.addRow(QLabel('Icons Path'), self.icons_install_loc)
        options_layout.addRow(QLabel('Shelf Name'), self.shelf_name)

        # Add all the paths to the dropdown options.
        script_paths: list = os.getenv('MAYA_SCRIPT_PATH').split(';')
        icon_paths: list = os.getenv('XBMLANGPATH').split(';')

        # Add all aviliable install paths in excluding system paths
        for path in filter(lambda x: '/Program' not in x and len(x) > 0, script_paths):
            self.scripts_install_loc.addItem(path)
        for path in filter(lambda x: '/Program' not in x and len(x) > 0, icon_paths):
            self.icons_install_loc.addItem(path)

        # Main operation buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.setContentsMargins(0, 20, 0, 0)
        cancel_btn = QPushButton('Cancel', objectName='cancel-btn', fixedHeight=50)
        self.install_btn = QPushButton('Install', objectName='install-btn', fixedHeight=50)

        cancel_btn.clicked.connect(lambda: self.close())
        self.install_btn.clicked.connect(lambda: self.install())

        buttons_layout.addWidget(self.install_btn)
        buttons_layout.addWidget(cancel_btn)

        # Create heading layout and labels
        heading = QVBoxLayout(alignment=Qt.AlignHCenter)
        heading.addWidget(QLabel('<h1>Cirkus Toolbox</h1>', alignment=Qt.AlignHCenter))
        heading.addWidget(QLabel('Select what tools you want to install and where they should be installed.'
                                 'All the available paths are defined as maya environment paths.',
                                 wordWrap=True, fixedHeight=50, fixedWidth=290, alignment=Qt.AlignTop))

        # Add all the layouts and set it to the widget
        layout.addLayout(heading)
        layout.addLayout(self._ui_install_build())
        layout.addLayout(options_layout)
        layout.addWidget(QLabel('<h3 align="center">Available Tools to Install</h3>'))
        # layout.addLayout(modules_layout)
        layout.addWidget(self._tools_list_widget)
        layout.addStretch()
        layout.addLayout(buttons_layout)

        # Create base widgets to act as panels to switch between
        self._install_splash = self._ui_install_progress_splash()
        self._options_panel = QWidget(layout=layout)
        self._install_splash.setVisible(False)

        # Add the panels to a root layout
        root_layout = QVBoxLayout()
        root_layout.addWidget(self._options_panel)
        root_layout.addWidget(self._install_splash)

        self.setLayout(root_layout)

    def set_panel(self, panel: str):
        """
        Sets the panel to either the main options panel or install splash.
        If panel is set to install then the install panel will be shown
        otherwise the main panel is displayed.
        """
        self._install_splash.setVisible('install' in panel)
        self._options_panel.setVisible('install' not in panel)

        if self._install_splash.isVisible():
            self.setFixedHeight(200)
        else:
            self.setMaximumHeight(0)
            self.setMinimumHeight(0)

    def install(self):
        """
        Runs the installer
        """
        # Handle invalid data to install from
        if self._toolbox_data is None:
            return

        # Change Window to installing splash
        self.set_panel('install')

        # Create a shelf
        shelf_name = self.shelf_name.text()
        if shelf_name == '':
            shelf_name = 'CoolTool'
        create_shelf(shelf_name)
        remove_shelf_button(shelf_name, 'ALL')

        # Loop over all checked tools and install them
        widgets = self._tools_list_widget.list()
        tools_pending = []

        w: ToolButtonWidget
        for w in widgets:
            if w.isChecked():
                tools_pending.append(w.text())

        try:
            self._progress_widget.setProperty('error', False)
            self._progress_widget.setStyleSheet('/*/')
            # Create installer instance and start it
            Installer(shelf_name, self._toolbox_data, tools_pending,
                      {
                          'is_local': self.is_local_install,
                          'path': self._local_toolbox_dir
                      },
                      self.scripts_install_loc.currentText(),
                      self.icons_install_loc.currentText(),
                      self._progress_widget,
                      self._install_status).start()
        except Exception as e:
            self._progress_widget.setProperty('error', True)
            self._progress_widget.setStyleSheet('/*/')
            self._install_status.setText('There was an error while installing.')
            print('There was an error Installing the tools:', e)
            print(traceback.format_exc())
            return
        self.close()

    def _load_tools(self, shelves: Optional[dict]):
        """
        Loads all the tools into memory and updates the UI elements to reflect all
        the aviliable tools that can be installed.
        """
        self._toolbox_data = shelves

        # Remove all old widgets from list
        self._tools_list_widget.reset()

        if shelves is None:
            return

        # Update UI Elements
        for tool in shelves:
            widget = ToolButtonWidget(tool, parent=self)
            tool_data = self._toolbox_data[tool]
            widget.setChecked(True)
            if 'checkStatus' in tool_data:
                check_state = tool_data['checkStatus']
                widget.setChecked(check_state)
                if check_state == 2:
                    widget.setDisabled(True)
            self._tools_list_widget.addWidget(widget)

    def _fetch_tools_data(self):
        """
        Fetches the data for the installer. This will check in multiple
        locations depending on if it is being selected as a remote or local
        installiation.
        """
        # Attempt to download remote data.
        if self._remote_data is None:
            from urllib.error import HTTPError
            try:
                shelf = download_data(f'{_REPO}toolboxShelf.json')
                self._remote_data = json.loads(shelf)
            except HTTPError:
                cmds.warning('Failted to download remote data.')

        # Attempt to download the tool's data from the repo online.
        if not self.is_local_install:
            self._load_tools(self._remote_data)
            return

        # Load from file
        if self._local_toolbox_dir is not None:
            file = os.path.join(self._local_toolbox_dir, 'toolboxShelf.json')
            with open(file, 'r') as content:
                self._load_tools(json.loads(content.read()))


def open_window():
    installer = InstallerWindow()
    installer.show()


if __name__ == '__main__':
    open_window()
