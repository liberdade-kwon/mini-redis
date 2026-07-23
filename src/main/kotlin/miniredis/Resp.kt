package miniredis

object Resp {
    // 반환: 명령 하나(List<String>) or null(데이터 부족 — acc 보존)
    fun tryParse(acc: StringBuilder): List<String>? {
        var pos = 0
        // 0 1 2 3  4 5 6 7  8 9 10 11 12 13
        // * 4 \r\n $ 4 \r\n P I N   G \r \n
        // 1) 배열 헤더 "*N\r\n"
        if (acc.isEmpty() || acc[0] != '*') return null
        val headEnd = acc.indexOf("\r\n", pos)
        if (headEnd == -1) return null                                // ② 부족 → null
        val count = acc.substring(1, headEnd).toIntOrNull() ?: return null  // ④ 자릿수 무관
        pos = headEnd + 2                                             // ⑤ \r\n 건너뛰기

        // 2) bulk string × count
        val parts = mutableListOf<String>()
        repeat(count) {                                               // ③ 정확히 N번
            if (pos >= acc.length || acc[pos] != '$') return null
            val lenEnd = acc.indexOf("\r\n", pos)
            if (lenEnd == -1) return null                             // ②
            val len = acc.substring(pos + 1, lenEnd).toIntOrNull() ?: return null  // ④⑥ (0 허용)
            pos = lenEnd + 2

            if (acc.length < pos + len + 2) return null               // ② 데이터+\r\n 도착 확인
            parts.add(acc.substring(pos, pos + len))                  // 길이 기반 — \r\n 포함돼도 안전
            pos += len + 2
        }

        acc.delete(0, pos)                                            // ① 커밋 — 성공 시 단 한 번
        return parts
    }
}