package miniredis

object Commands {

    private val keyspace = mutableMapOf<String, String>()     // 전역 키스페이스 (락 불필요 — 왜인지 설명할 수 있어야 함)

    // 명령 하나의 정의: 핸들러 + 인자 개수 규칙
    private class CommandSpec(
        val arity: Int,                               // 명령 포함 총 인자 수. SET=3, GET=2, PING=1, ECHO=2
        val handler: (List<String>) -> String
    )

    private val commandTable = mapOf(
        "PING" to CommandSpec(1) { "+PONG\r\n" },
        "ECHO" to CommandSpec(2) { parts ->
            val msg = parts[1]
            val len = msg.toByteArray().size    // 문자 수 아닌 바이트 수 (치트시트의 그 함정)
            "\$$len\r\n$msg\r\n"                // Kotlin에서 $ 문자는 \$로 이스케이프
        },
        "SET"  to CommandSpec(3) { parts ->
            keyspace[parts[1]] = parts[2]
            "+OK\r\n"
        },
        "GET"  to CommandSpec(2) { parts ->
            val ans = keyspace[parts[1]] ?:return@CommandSpec "$-1\r\n"
            "\$${ans.length}\r\n$ans\r\n"
        },
    )

    fun execute(parts: List<String>): String {
        val name = parts[0].uppercase()
        val spec = commandTable[name] ?: return "-ERR unknown command '${parts[0]}'\r\n"
        if (parts.size != spec.arity) return "-ERR wrong number of arguments for '${parts[0]}' command\r\n"

        return spec.handler(parts)
    }
}