import html.parser
class MyParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.log = []
    def handle_starttag(self, tag, attrs):
        if tag == 'div':
            id_attr = next((v for k, v in attrs if k == 'id'), None)
            class_attr = next((v for k, v in attrs if k == 'class'), None)
            self.stack.append({'line': self.getpos()[0], 'id': id_attr, 'class': class_attr})
            self.log.append(f"OPEN: L{self.getpos()[0]} depth={len(self.stack)}")
    def handle_endtag(self, tag):
        if tag == 'div':
            if self.stack:
                popped = self.stack.pop()
                self.log.append(f"CLOSE: L{self.getpos()[0]} (matches L{popped['line']}) depth={len(self.stack)}")
                if len(self.stack) == 0:
                    self.log.append(f"*** STACK EMPTY AT LINE {self.getpos()[0]} ***")
            else:
                self.log.append(f"UNMATCHED CLOSE: L{self.getpos()[0]}")
parser = MyParser()
with open(r'e:\djacc\templates\reports\rep_dashboard.html', 'r', encoding='utf-8') as f:
    parser.feed(f.read())
for line in parser.log[-100:]:
    print(line)
