from PyQt5.QtCore import QObject, pyqtSignal,pyqtSlot
import os
import os.path
import pathlib

import logging
import time
import json
import traceback

import datetime

class Upload(QObject):
    """ Background thread to handle uploading content """

    progress = pyqtSignal(str, int, int)
    finished = pyqtSignal(int)
    error = pyqtSignal(str)
    _trigger = pyqtSignal()

    def __init__(self, tator, mediaList, section):
        super(Upload, self).__init__()
        self.tator = tator
        self.section = section
        self.mediaList = mediaList
        self._trigger.connect(self._process)
        self._terminated=True

    def start(self):
        self._terminated=False
        self._trigger.emit()

    def stop(self):
        self._terminated=True

    @pyqtSlot()
    def _process(self):
        total = len(self.mediaList)
        chunk_size = 20 * 1024 * 1024
        try:
            for idx,media in enumerate(self.mediaList):
                self.progress.emit(os.path.basename(media), 0, idx)
                last=None
                for chunk in self.tator.Media.uploadFile_v2(media,
                                                            section=self.section,
                                                            chunk_size=chunk_size):
                    if self._terminated:
                        return
                    if last:
                        now = datetime.datetime.now()
                        delta = now-last
                        last = now
                        if delta.seconds:
                            throughput = chunk_size / 1024 / 1024 / delta.seconds
                            print(f"Throughput = {throughput} Mbps")
                        self.progress.emit(os.path.basename(media), 1, round(chunk))
                    else:
                        last = datetime.datetime.now()
                        self.progress.emit(os.path.basename(media), 1, round(chunk))
                if self._terminated:
                    return
            self.finished.emit(len(self.mediaList))
        except Exception as e:
            self.error.emit(str(e))
            print(traceback.format_exc())