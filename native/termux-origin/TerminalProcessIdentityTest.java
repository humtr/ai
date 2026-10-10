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
}
