import sys
import json
import os
import platform
import subprocess
from datetime import datetime
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QListWidget, QVBoxLayout, QWidget, QComboBox, 
    QLabel, QHBoxLayout, QPushButton, QFileDialog, QMessageBox, QProgressBar, 
    QFrame, QScrollArea
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QIcon
import re
from logs import LogsDialog

class ConversionProgress(QFrame):
    def __init__(self, filename, parent=None):
        super().__init__(parent)
        self.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Raised)
        
        layout = QVBoxLayout(self)
        
        # Filename label
        self.filename_label = QLabel(os.path.basename(filename))
        self.filename_label.setWordWrap(True)
        layout.addWidget(self.filename_label)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        # Status label
        self.status_label = QLabel("Waiting...")
        layout.addWidget(self.status_label)

class ConverterThread(QThread):
    progress_updated = pyqtSignal(str, int)  # filename, progress
    conversion_finished = pyqtSignal(str, str)  # input_file, output_file
    status_updated = pyqtSignal(str, str)  # filename, status

    def __init__(self, input_file, output_file, ffmpeg_path):
        super().__init__()
        self.input_file = input_file
        self.output_file = output_file
        self.ffmpeg_path = ffmpeg_path

    def run(self):
        self.status_updated.emit(self.input_file, "Starting conversion...")
        command = [
            self.ffmpeg_path,
            '-i', self.input_file,
            '-progress', 'pipe:1',
            '-nostats',
            self.output_file
        ]
        
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1
        )

        duration = None
        for line in process.stderr:
            if duration is None:
                duration_match = re.search(r"Duration: (\d{2}):(\d{2}):(\d{2}\.\d{2})", line)
                if duration_match:
                    hours = int(duration_match.group(1))
                    minutes = int(duration_match.group(2))
                    seconds = float(duration_match.group(3))
                    duration = (hours * 3600) + (minutes * 60) + seconds
                    break

        if duration:
            self.status_updated.emit(self.input_file, "Converting...")
            for line in process.stdout:
                time_match = re.search(r"out_time=(\d{2}):(\d{2}):(\d{2}\.\d{2})", line)
                if time_match:
                    hours = int(time_match.group(1))
                    minutes = int(time_match.group(2))
                    seconds = float(time_match.group(3))
                    current_time = (hours * 3600) + (minutes * 60) + seconds
                    progress = min(99, int((current_time / duration) * 100))
                    self.progress_updated.emit(self.input_file, progress)

        process.wait()
        if process.returncode == 0:
            self.progress_updated.emit(self.input_file, 100)  # Set to 100% when complete
            self.status_updated.emit(self.input_file, "Completed")
            self.conversion_finished.emit(self.input_file, self.output_file)
        else:
            self.status_updated.emit(self.input_file, "Error")
            print(f"Error converting {self.input_file}")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pkartor Converter")
        self.setGeometry(100, 100, 800, 600)
        self.setWindowIcon(QIcon("icon.ico"))

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Queue section
        queue_label = QLabel("Conversion Queue:")
        main_layout.addWidget(queue_label)
        
        self.list_widget = QListWidget(self)
        self.list_widget.setAcceptDrops(False)
        main_layout.addWidget(self.list_widget)

        # Progress section
        progress_label = QLabel("Active Conversions:")
        main_layout.addWidget(progress_label)
        
        self.progress_widget = QWidget()
        self.progress_layout = QVBoxLayout(self.progress_widget)
        self.progress_frames = {}  # Store progress frames by filename
        
        progress_scroll = QScrollArea()
        progress_scroll.setWidget(self.progress_widget)
        progress_scroll.setWidgetResizable(True)
        main_layout.addWidget(progress_scroll)

        # Controls section
        controls_layout = QHBoxLayout()
        main_layout.addLayout(controls_layout)

        self.input_label = QLabel("Input Extension:")
        controls_layout.addWidget(self.input_label)

        self.input_combo_box = QComboBox(self)
        controls_layout.addWidget(self.input_combo_box)

        self.output_label = QLabel("Output Extension:")
        controls_layout.addWidget(self.output_label)

        self.output_combo_box = QComboBox(self)
        controls_layout.addWidget(self.output_combo_box)

        buttons_layout = QHBoxLayout()
        main_layout.addLayout(buttons_layout)

        self.add_files_button = QPushButton("📂 Add Files")
        self.add_files_button.clicked.connect(self.add_files)
        buttons_layout.addWidget(self.add_files_button)

        self.settings_button = QPushButton("🎛️ Settings")
        self.settings_button.clicked.connect(self.open_settings)
        buttons_layout.addWidget(self.settings_button)

        self.logs_button = QPushButton("📄 Logs")
        self.logs_button.clicked.connect(self.show_logs)
        buttons_layout.addWidget(self.logs_button)

        self.convert_button = QPushButton("▶️ Convert")
        self.convert_button.clicked.connect(self.handle_convert)
        buttons_layout.addWidget(self.convert_button)

        self.media_formats = self.load_media_formats()
        self.supported_extensions = set()
        self.load_supported_extensions()
        self.setAcceptDrops(True)
        self.ffmpeg_path = self.get_ffmpeg_path()
        self.converter_threads = {}  # Store threads by filename
        self.log_dir = self.ensure_log_directory()
        self.log_file = os.path.join(self.log_dir, datetime.now().strftime("%Y-%m-%d.log"))

    def load_supported_extensions(self):
        """Load all supported file extensions from media formats"""
        for format_data in self.media_formats.values():
            self.supported_extensions.update(format_data["extensions"])

    def ensure_log_directory(self):
        logs_dir = os.path.join(os.getcwd(), "logs")
        os.makedirs(logs_dir, exist_ok=True)
        return logs_dir

    def load_media_formats(self):
        try:
            with open("settings.json", "r") as f:
                data = json.load(f)
                return data.get("media_formats", {})
        except Exception as e:
            print(f"Error loading settings: {e}")
            return {}

    def get_ffmpeg_path(self):
        current_os = platform.system()
        if current_os == "Windows":
            ffmpeg_path = os.path.join(os.getcwd(), "ffmpeg", "ffmpeg.exe")
        elif current_os in ["Linux", "Darwin"]:
            ffmpeg_path = "ffmpeg"
        else:
            raise Exception(f"Unsupported OS: {current_os}")

        if not os.path.exists(ffmpeg_path) and current_os == "Windows":
            print(f"FFmpeg executable not found at: {ffmpeg_path}")
            return None
        return ffmpeg_path

    def update_progress(self, filename, progress):
        if filename in self.progress_frames:
            self.progress_frames[filename].progress_bar.setValue(progress)

    def update_status(self, filename, status):
        if filename in self.progress_frames:
            self.progress_frames[filename].status_label.setText(status)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            for url in urls:
                file_path = url.toLocalFile()
                file_ext = f".{file_path.split('.')[-1].lower()}"
                if file_ext in self.supported_extensions:
                    self.list_widget.addItem(file_path)
                    self.update_input_combo_box(file_path)
                    self.update_output_combo_box(file_path)
                else:
                    print(f"File {file_path} is not supported")

    def update_input_combo_box(self, input_file):
        input_extension = f".{input_file.split('.')[-1].lower()}"
        if input_extension not in [self.input_combo_box.itemText(i) for i in range(self.input_combo_box.count())]:
            self.input_combo_box.addItem(input_extension)

    def update_output_combo_box(self, input_file):
        input_extension = f".{input_file.split('.')[-1].lower()}"
        self.output_combo_box.clear()

        for format, data in self.media_formats.items():
            if input_extension in data["extensions"]:
                self.output_combo_box.addItems(data["convertible_to"])

        if self.output_combo_box.count() == 0:
            self.output_combo_box.addItem("No available formats")

    def convert_file(self, input_file, output_ext):
        output_file = input_file.rsplit('.', 1)[0] + output_ext
        base_output_file = output_file
        counter = 1
        while os.path.exists(output_file):
            output_file = f"{base_output_file.rsplit('.', 1)[0]}_{counter}.{output_ext.lstrip('.')}"
            counter += 1

        # Create progress frame
        progress_frame = ConversionProgress(input_file)
        self.progress_layout.addWidget(progress_frame)
        self.progress_frames[input_file] = progress_frame

        # Create and start converter thread
        converter_thread = ConverterThread(input_file, output_file, self.ffmpeg_path)
        converter_thread.progress_updated.connect(self.update_progress)
        converter_thread.status_updated.connect(self.update_status)
        converter_thread.conversion_finished.connect(self.on_conversion_finished)
        converter_thread.finished.connect(lambda: self.on_thread_finished(input_file))
        
        self.converter_threads[input_file] = converter_thread
        converter_thread.start()

    def handle_convert(self):
        output_ext = self.output_combo_box.currentText()
        input_ext = self.input_combo_box.currentText()

        if not output_ext:
            QMessageBox.warning(self, "Output Format", "Please select an output format!")
            return

        if not input_ext:
            QMessageBox.warning(self, "Input Format", "Please select an input format!")
            return

        if self.ffmpeg_path is None:
            QMessageBox.critical(self, "FFmpeg Error", "FFmpeg is not available, conversion failed.")
            return

        # Get items to remove (matching input extension)
        items_to_remove = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.text().endswith(input_ext):
                items_to_remove.append((i, item.text()))

        # Process files and remove them from queue
        for index, input_file in reversed(items_to_remove):
            self.convert_file(input_file, output_ext)
            self.list_widget.takeItem(index)

        # Only clear the input combo box if no items remain in the list
        if self.list_widget.count() == 0:
            self.input_combo_box.clear()

    def add_files(self):
        file_dialog = QFileDialog(self)
        file_dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
        
        # Create filter string from supported extensions
        filter_str = "Media files ("
        filter_str += " ".join(f"*{ext}" for ext in self.supported_extensions)
        filter_str += ")"
        
        file_dialog.setNameFilter(filter_str)
        
        if file_dialog.exec():
            files = file_dialog.selectedFiles()
            for file in files:
                file_ext = f".{file.split('.')[-1].lower()}"
                if file_ext in self.supported_extensions:
                    self.list_widget.addItem(file)
                    self.update_input_combo_box(file)
                    self.update_output_combo_box(file)
                else:
                    QMessageBox.warning(
                        self,
                        "Unsupported Format",
                        f"The file format '{file_ext}' is not supported."
                    )

    def on_conversion_finished(self, input_file, output_file):
        print(f"Conversion finished: {input_file} -> {output_file}")

        # Log the conversion
        with open(self.log_file, "a") as log:
            log.write(f"{datetime.now()}: {input_file} -> {output_file}\n")

    def on_thread_finished(self, input_file):
        if input_file in self.converter_threads:
            del self.converter_threads[input_file]

        if input_file in self.progress_frames:
            progress_frame = self.progress_frames[input_file]
            self.progress_layout.removeWidget(progress_frame)
            progress_frame.deleteLater()
            del self.progress_frames[input_file]

    def show_logs(self):
        logs_dialog = LogsDialog(self.log_file, self)
        logs_dialog.exec()

    def open_settings(self):
        QMessageBox.information(self, "Settings", "Settings functionality will be implemented here.")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())