package miniredis

import java.net.InetSocketAddress
import java.nio.ByteBuffer
import java.nio.channels.SelectionKey
import java.nio.channels.Selector
import java.nio.channels.ServerSocketChannel
import java.nio.channels.SocketChannel

/**
 * mini-redis 진입점.
 *
 * Stage 1 목표: 6379 포트에 바인드하고, 접속한 클라이언트가 보내는
 * PING 명령에 +PONG\r\n 으로 응답한다.
 *
 * Stage 1에서는 블로킹 I/O(java.net.ServerSocket)를 써도 된다.
 * (Stage 2에서 java.nio Selector 기반 이벤트 루프로 재작성할 예정)
 */
fun main(args: Array<String>) {
    val port = args.getOrNull(0)?.toIntOrNull() ?: 6379
    println("mini-redis starting on port $port")

    // TODO: Stage 1 — 여기부터 구현
    val selector = Selector.open()
    val channel = ServerSocketChannel.open()
    channel.bind(InetSocketAddress(port))
    channel.configureBlocking(false)
    channel.register(selector, SelectionKey.OP_ACCEPT)

    while (true) {
        val readyCount = selector.select()
        if (readyCount == 0) continue

        val keyIterator = selector.selectedKeys().iterator()
        while (keyIterator.hasNext()) {
            val key = keyIterator.next()
            keyIterator.remove()

            if (key.isAcceptable) {
                val serverChannel = key.channel() as ServerSocketChannel
                val clientChannel = serverChannel.accept() as SocketChannel
                clientChannel.configureBlocking(false)                        // register 전 필수
                val clientKey = clientChannel.register(selector, SelectionKey.OP_READ)
                clientKey.attach(StringBuilder())                             // 이 클라이언트 전용 누적 버퍼

            } else if (key.isReadable) {
                val clientChannel = key.channel() as SocketChannel
                val acc = key.attachment() as StringBuilder      // accept 때 붙여둔 그 버퍼
                val buf = ByteBuffer.allocate(1024)
                try {
                    val n = clientChannel.read(buf)
                    when {
                        n == -1 -> {
                            key.cancel()
                            clientChannel.close()
                        }
                        n > 0 -> {
                            buf.flip()
                            val bytes = ByteArray(buf.remaining())   // remaining() = 꺼낼 수 있는 바이트 수 (= n)
                            buf.get(bytes)                           // 버퍼 → 배열로 꺼내기
                            val text = String(bytes)                 // 문자열화 (기본 UTF-8)
                            acc.append(text)

                            while (true) {
                                val idx = acc.indexOf("\n")
                                if (idx == -1) break                     // 완성된 줄 없음 → 여기서 멈추고
                                // 나머지는 acc에 남긴 채 다음 READ 이벤트를 기다림
                                val line = acc.substring(0, idx)         // 완성된 줄 하나 (끝에 \r 붙어있을 수 있음)
                                acc.delete(0, idx + 1)                   // 꺼낸 만큼 acc에서 실제로 제거 (\n까지 포함해서 +1)
                                if (line.trim() == "PING") {             // \r 제거 후 비교 — 어제 배운 그것
                                    clientChannel.write(ByteBuffer.wrap("+PONG\r\n".toByteArray()))
                                }
                            }
                        }
                    }
                } catch (e: Exception) {
                    clientChannel.close()
                }
            }
        }
    }
}
