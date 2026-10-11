// SPDX-License-Identifier: GPL-3.0-or-later
package com.termux.app;
import org.junit.Test;
import static org.junit.Assert.*;
public class TerminalProcessIdentityTest {
    private String stat(String parent, String start) {
        return "77 (name with ) parentheses) S " + parent + " 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 " + start;
    }
    @Test public void identityUsesKernelStartAndHandlesParentheses() {
        TerminalProcessIdentity p = TerminalProcessIdentity.parse(stat("42", "901"));
        assertEquals(42, p.parent); assertEquals(901, p.start);
    }
    @Test public void malformedAndRecycledIdentityCannotBecomeValidReference() {
        for (String input : new String[]{"", "77 missing", stat("-1", "2"), stat("x", "2"), stat("1", "0"), stat("1", "x")}) {
            try { TerminalProcessIdentity.parse(input); fail(input); }
            catch (IllegalArgumentException expected) { }
        }
        assertNotEquals(TerminalProcessIdentity.parse(stat("1", "123")).start,
                        TerminalProcessIdentity.parse(stat("1", "124")).start);
    }
    @Test public void referenceNumbersAreCanonicalAndBounded() {
        assertEquals(123, TerminalProcessIdentity.positive("123"));
        for (String value : new String[]{"", "0", "-1", "+1", "01", "1x", "999999999999999999999"}) {
            try { TerminalProcessIdentity.positive(value); fail(value); }
            catch (IllegalArgumentException expected) { }
        }
    }
    @Test public void originStopsBeforeProtectedApplicationParent() throws Exception {
        java.util.List<Integer> reads = new java.util.ArrayList<>();
        int[] chain = TerminalProcessIdentity.ancestry(30, 10, pid -> {
            reads.add(pid);
            if (pid == 30) return new TerminalProcessIdentity(20, 301);
            if (pid == 20) return new TerminalProcessIdentity(10, 201);
            throw new java.io.IOException("protected Android parent");
        });
        assertArrayEquals(new int[]{30, 20}, chain);
        assertEquals(java.util.Arrays.asList(30, 20), reads);
    }
    @Test public void detachedAndCyclicOriginsRemainUnavailable() throws Exception {
        for (int mode : new int[]{0, 1, 2}) {
            final int selected = mode;
            try {
                TerminalProcessIdentity.ancestry(30, 10, pid -> new TerminalProcessIdentity(
                    selected == 0 ? 0 : selected == 1 ? pid : pid == 30 ? 20 : 30, 301));
                fail("unbound origin");
            } catch (IllegalStateException expected) { }
        }
    }
    @Test public void inaccessibleOriginDoesNotGainAuthority() throws Exception {
        try {
            TerminalProcessIdentity.ancestry(30, 10, pid -> { throw new java.io.IOException("denied"); });
            fail("inaccessible origin");
        } catch (java.io.IOException expected) { }
    }
}
