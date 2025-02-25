from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTextEdit
from datetime import datetime

class LogsDialog(QDialog):
    def __init__(self, log_file, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Conversion Logs")
        self.setGeometry(150, 150, 600, 400)
        
        # Create layout
        layout = QVBoxLayout(self)
        
        # Create text edit widget
        self.log_text_edit = QTextEdit()
        self.log_text_edit.setReadOnly(True)
        layout.addWidget(self.log_text_edit)
        
        # Load and display logs
        self.load_logs(log_file)
    
    def load_logs(self, log_file):
        try:
            with open(log_file, "r") as file:
                log_content = file.read()
                self.log_text_edit.setText(log_content)
        except Exception as e:
            self.log_text_edit.setText(f"Error reading log file: {e}")