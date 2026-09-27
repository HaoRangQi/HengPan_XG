"""
给 baostock 客户端打补丁，修掉它收包循环里的死循环。

baostock 0.9.4 的 `util/socketutil.py::send_msg` 是这样收数据的：

    receive = b""
    while True:
        recv = default_socket.recv(8192)
        receive += recv
        if receive[-13:] == b"<![CDATA[]]>\\n":
            break

连接一旦断开（服务端主动断、网络中断、代理把连接掐了），`recv` 会**立即**返回空字节
而不是阻塞，但循环只认结束标记才退出，于是就地空转：CPU 吃满、函数永不返回。
`socket.setdefaulttimeout` 救不了这种情况——recv 根本没有阻塞，不会触发超时。

实测后果：扫描被取消后，收尾的 logout 卡在这里，任务状态永远停在「正在停止扫描…」，
后端进程空转了 10 多个小时。

这里替换整个 `send_msg`：收到空字节即判定连接已断并抛异常，交给上层的重试/中止逻辑处理。
所有调用方都是 `import baostock.util.socketutil as sock` 再 `sock.send_msg(...)`，
替换模块属性即可对全部调用生效。

导入本模块就会自动打上补丁（幂等，重复导入不会叠加）。
"""
import zlib

import baostock.common.contants as cons
import baostock.common.context as context
import baostock.util.socketutil as socketutil

_PATCH_FLAG = "_hengpan_patched"
# 单次 send_msg 最多等这么久（秒），防止服务端只发一半就不动了
RECV_TIMEOUT = 60


class BaostockConnectionLost(ConnectionError):
    """baostock 连接已断开：recv 返回空字节。"""


def _send_msg(msg):
    """send_msg 的替代实现：连接断开时抛异常，不再空转。"""
    if not hasattr(context, "default_socket"):
        raise BaostockConnectionLost("baostock 尚未登录")
    default_socket = getattr(context, "default_socket")
    if default_socket is None:
        raise BaostockConnectionLost("baostock 连接不存在")

    default_socket.settimeout(RECV_TIMEOUT)
    default_socket.send(bytes(msg + "\n", encoding="utf-8"))

    receive = b""
    while True:
        chunk = default_socket.recv(8192)
        if not chunk:
            # 原实现在这里会无限空转，这是本补丁要解决的问题
            raise BaostockConnectionLost("baostock 连接已被对端关闭")
        receive += chunk
        if receive[-13:] == b"<![CDATA[]]>\n":
            break

    head_str = bytes.decode(receive[0:cons.MESSAGE_HEADER_LENGTH])
    head_arr = head_str.split(cons.MESSAGE_SPLIT)
    if head_arr[1] in cons.COMPRESSED_MESSAGE_TYPE_TUPLE:
        body_length = int(head_arr[2])
        body = receive[cons.MESSAGE_HEADER_LENGTH:cons.MESSAGE_HEADER_LENGTH + body_length]
        return head_str + bytes.decode(zlib.decompress(body))
    return bytes.decode(receive)


def apply_patch():
    """打补丁；已经打过就直接返回。"""
    if getattr(socketutil.send_msg, _PATCH_FLAG, False):
        return
    setattr(_send_msg, _PATCH_FLAG, True)
    socketutil.send_msg = _send_msg


apply_patch()
