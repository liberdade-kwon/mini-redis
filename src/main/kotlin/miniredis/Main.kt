package miniredis

import java.io.IOException
import java.net.InetSocketAddress
import java.net.ServerSocket
import java.net.SocketException

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
    val socket = ServerSocket(port)

    while (true) {
        val client = socket.accept()

        client.use {
            val bufferedReader = it.getInputStream().bufferedReader()
            val bufferedWriter = it.getOutputStream().bufferedWriter()
            try {
                while (true) {
                    val request = bufferedReader.readLine() ?: break
                    if (request == "PING") {
                        bufferedWriter.write("+PONG\r\n")
                        bufferedWriter.flush()
                    }
                }
            } catch (ex: SocketException) {

            }
        }
    }
}
