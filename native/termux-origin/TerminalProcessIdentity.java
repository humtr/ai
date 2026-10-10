// SPDX-License-Identifier: GPL-3.0-or-later
package com.termux.app;

import java.io.FileInputStream;
import java.nio.charset.StandardCharsets;

final class TerminalProcessIdentity {
    final int parent;
    final long start;
    TerminalProcessIdentity(int parent, long start) { this.parent = parent; this.start = start; }
    static TerminalProcessIdentity parse(String value) {
        int end = value.lastIndexOf(')');
        if (end < 0) throw new IllegalArgumentException("invalid process identity");
        String[] fields = value.substring(end + 1).trim().split("\\s+");
        if (fields.length < 20) throw new IllegalArgumentException("invalid process identity");
        int parent = Integer.parseInt(fields[1]);
        long start = Long.parseLong(fields[19]);
        if (parent < 0 || start <= 0) throw new IllegalArgumentException("invalid process identity");
        return new TerminalProcessIdentity(parent, start);
    }
    static TerminalProcessIdentity read(int pid) throws Exception {
        if (pid <= 0) throw new IllegalArgumentException("invalid process identity");
        try (FileInputStream stream = new FileInputStream("/proc/" + pid + "/stat")) {
            byte[] data = new byte[8193]; int length = stream.read(data);
            if (length <= 0 || length > 8192) throw new IllegalArgumentException("invalid process identity");
            return parse(new String(data, 0, length, StandardCharsets.UTF_8));
        }
    }
    static long positive(String value) {
        if (!value.matches("[1-9][0-9]*")) throw new IllegalArgumentException("invalid terminal reference");
        long result = Long.parseLong(value);
        if (result <= 0) throw new IllegalArgumentException("invalid terminal reference");
        return result;
    }
}
