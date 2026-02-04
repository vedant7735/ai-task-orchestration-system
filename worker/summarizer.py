from .worker import Worker
class SummarizerWorker(Worker):
    def __init__(self, temperature=0.5):
        super().__init__("Summarizer", temperature)