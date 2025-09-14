import logging
import queue

class UILogHandler(logging.Handler):
    def __init__(self, log_widget):
        super().__init__()
        self.log_widget = log_widget
        self.log_queue = queue.Queue()
        self._start_polling()

    def emit(self, record):
        msg = record.msg 
        if isinstance(msg, dict):
            self.log_queue.put(msg)
        else:
            self.log_queue.put(self.format(record))
    def _start_polling(self):
        def poll():
            while not self.log_queue.empty():
                msg = self.log_queue.get()
                self.log_widget.add_log(msg)
            self.log_widget.after(100, poll)

        self.log_widget.after(100, poll)
