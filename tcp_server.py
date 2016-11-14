# coding: utf8
import json
import socket
import tornado.gen
import tornado.ioloop
import tornado.iostream
from tornado.queues import Queue
from tornado.httpserver import HTTPServer
from tornado.tcpserver import TCPServer
from tornado.web import RequestHandler
from tornado.websocket import WebSocketHandler


class AppTcpClient(object):
    def connect_service(self, source_name):
        self.name = source_name

    def disconnect_service(self):
        self.name = None

    def __init__(self, stream, app_queue):
        super(AppTcpClient, self).__init__()
        self.stream = stream
        self.app_queue = app_queue
        self.name = None

        self.stream.socket.setsockopt(
            socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.stream.socket.setsockopt(
            socket.IPPROTO_TCP, socket.SO_KEEPALIVE, 1)
        self.stream.set_close_callback(self.on_disconnect)

    @tornado.gen.coroutine
    def on_disconnect(self):
        yield []

    @tornado.gen.coroutine
    def dispatch_client(self):
        try:
            while True:
                line = yield self.stream.read_until(b'\n')
                line = line.decode('utf-8').strip()
                if line == u'End':
                    self.stream.write(('End %s' % self.name).encode('utf-8'))
                    self.disconnect_service()
                else:
                    kv_list = line.split(u':: ')
                    if len(kv_list)==2:
                        if not self.name and kv_list[0] == u'Auth':
                            self.connect_service(kv_list[1])
                            self.stream.write((u'Auth %s' % self.name).encode('utf-8'))
                        elif self.name:
                            message = json.dumps({
                                'service': self.name,
                                'key': kv_list[0],
                                'value': kv_list[1]
                            })
                            self.app_queue.put(message)
                            self.stream.write(u'Ok'.encode('utf-8'))
                yield []
        except tornado.iostream.StreamClosedError:
            pass

    @tornado.gen.coroutine
    def on_connect(self):
        yield self.dispatch_client()


class AppTcpServer(TCPServer):
    def __init__(self, app_queue):
        super(AppTcpServer, self).__init__()
        self.app_queue = app_queue

    @tornado.gen.coroutine
    def handle_stream(self, stream, address):
        connection = AppTcpClient(stream, self.app_queue)
        yield connection.on_connect()


class AppWebSocketHandler(WebSocketHandler):
    def initialize(self, app_queue):
        self.app_queue = app_queue
        tornado.ioloop.IOLoop.instance().add_callback(self.watch)

    @tornado.gen.coroutine
    def watch(self):
        while True:
            message = yield self.app_queue.get()
            if message:
                self.write_message(message)


class MainHandler(RequestHandler):
    def get(self):
        self.render('templates/index.html')


def main():
    host = '0.0.0.0'
    tcp_port = 8008
    http_port = 8080

    app_queue = Queue(maxsize=0)

    server = AppTcpServer(app_queue)
    server.listen(tcp_port, host)
    print("TCP listening on %s:%d..." % (host, tcp_port))

    http_server = HTTPServer(
        tornado.web.Application([
            (r'/', MainHandler),
            (r'/websocket', AppWebSocketHandler, {'app_queue': app_queue})
        ], debug=True)
    )
    http_server.listen(http_port, host)
    print("HTTP listening on %s:%d..." % (host, http_port))

    tornado.ioloop.IOLoop.instance().start()


if __name__ == "__main__":
    main()