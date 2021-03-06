import sys
import json
import random
from runner import *
import os
import shutil
import queue
import threading
from initial_interconnect_survey import parse_xyi, parse_xysi
import time

def prep_all_routes(outfn, my_wire_to_quartus_wire):
    all_routes_to_try = {}

    all_my_wires = []
    for x in range(2, 9):
        for y in range(1, 5):
            if x >= 2 and x <= 7:
                if x != 2:
                    for nn in range(8):
                        all_my_wires.append(('L', x, y, nn))
                for nn in range(8):
                    all_my_wires.append(('R', x, y, nn))
                for nn in range(7):
                    all_my_wires.append(('U', x, y, nn))
                for nn in range(7):
                    all_my_wires.append(('D', x, y, nn))
            elif x == 8:
                for nn in range(8):
                    all_my_wires.append(('L', x, y, nn))
                for nn in range(8):
                    all_my_wires.append(('L2', x, y, nn))
                for nn in range(7):
                    all_my_wires.append(('U', x, y, nn))
                for nn in range(7):
                    all_my_wires.append(('D', x, y, nn))
    # Local interconnect into the IO cells
    for y in range(1, 5):
        for nn in range(18):
            all_my_wires.append(('LOCAL_INTERCONNECT', 1, y, nn))
            all_my_wires.append(('LOCAL_INTERCONNECT', 8, y, nn))
    for x in range(2, 8):
        for nn in range(10):
            all_my_wires.append(('LOCAL_INTERCONNECT', x, 0, nn))
            all_my_wires.append(('LOCAL_INTERCONNECT', x, 5, nn))
    # print(all_my_wires)
    # print(len(all_my_wires))

    for direction, dstX, dstY, dstI in all_my_wires:
        this_inputs = {}

        if direction == "LOCAL_INTERCONNECT" and (dstY == 0 or dstY == 5):
            # Column local interconnect
            if dstI < 5:
                # Next column hack
                dstX += 1

            for srcY in range(1, 5):
                for srcI in range(7):
                    this_inputs["U:X{}Y{}I{}".format(dstX, srcY, srcI)] = "maybe"
                    this_inputs["D:X{}Y{}I{}".format(dstX, srcY, srcI)] = "maybe"
            # "Left" part of the bottom IOs in this column
            if dstX != 8:
                for srcI in range(5):
                    this_inputs["U:X{}Y0I{}".format(dstX, srcI)] = "maybe"
            # "Right" part of the bottom IOs in the column to the left
            if dstX != 2:
                for srcI in range(5):
                    this_inputs["U:X{}Y0I{}".format(dstX - 1, srcI + 5)] = "maybe"
            # "Left" part of the top IOs in this column
            if dstX != 8:
                for srcI in range(5):
                    this_inputs["D:X{}Y5I{}".format(dstX, srcI)] = "maybe"
            # "Right" part of the top IOs in the column to the left
            if dstX != 2:
                for srcI in range(5):
                    this_inputs["D:X{}Y5I{}".format(dstX - 1, srcI + 5)] = "maybe"

            if dstI < 5:
                # Next column hack
                dstX -= 1
        else:
            if direction == "LOCAL_INTERCONNECT" and dstX == 1:
                # HACK
                dstX = 2

            # All up wires below this
            for srcY in range(1, dstY + 1):
                for srcI in range(7):
                    this_inputs["U:X{}Y{}I{}".format(dstX, srcY, srcI)] = "maybe"
            # "Left" part of the bottom IOs in this column
            if dstX != 8:
                for srcI in range(5):
                    this_inputs["U:X{}Y0I{}".format(dstX, srcI)] = "maybe"
            # "Right" part of the bottom IOs in the column to the left
            if dstX != 2:
                for srcI in range(5):
                    this_inputs["U:X{}Y0I{}".format(dstX - 1, srcI + 5)] = "maybe"

            # All down wires above this
            for srcY in range(dstY, 5):
                for srcI in range(7):
                    this_inputs["D:X{}Y{}I{}".format(dstX, srcY, srcI)] = "maybe"
            # "Left" part of the top IOs in this column
            if dstX != 8:
                for srcI in range(5):
                    this_inputs["D:X{}Y5I{}".format(dstX, srcI)] = "maybe"
            # "Right" part of the top IOs in the column to the left
            if dstX != 2:
                for srcI in range(5):
                    this_inputs["D:X{}Y5I{}".format(dstX - 1, srcI + 5)] = "maybe"

            # All right wires to the left of this (including IOs)
            for srcX in range(1, min(8, dstX + 1)):
                for srcI in range(8):
                    this_inputs["R:X{}Y{}I{}".format(srcX, dstY, srcI)] = "maybe"

            # All left wires to the right of this (IOs not fully understood)
            for srcX in range(max(3, dstX), 9):
                for srcI in range(8):
                    this_inputs["L:X{}Y{}I{}".format(srcX, dstY, srcI)] = "maybe"
            for srcI in range(8):
                this_inputs["L2:X8Y{}I{}".format(dstY, srcI)] = "maybe"

        if direction == "LOCAL_INTERCONNECT":
            if dstX == 2 and dstY != 0 and dstY != 5:
                dstX = 1
            all_routes_to_try["{}:X{}Y{}S0I{}".format(direction, dstX, dstY, dstI)] = this_inputs
        else:
            all_routes_to_try["{}:X{}Y{}I{}".format(direction, dstX, dstY, dstI)] = this_inputs

    for k, v in all_routes_to_try.items():
        if k.startswith("LOCAL_INTERCONNECT"):
            continue
        if k not in my_wire_to_quartus_wire:
            print(k)
        assert k in my_wire_to_quartus_wire
        for k in v:
            if k not in my_wire_to_quartus_wire:
                print(k)
            assert k in my_wire_to_quartus_wire

    # Remove self-routes lol
    for dst, srcs in all_routes_to_try.items():
        if dst in srcs:
            assert srcs[dst] != True
            del srcs[dst]

    # What do we already know?
    with open('initial-interconnect.json', 'r') as f:
        initial_interconnect_map = json.load(f)

    for dstnode, srcnodes in initial_interconnect_map.items():
        if dstnode.startswith("LOCAL_INTERCONNECT") and dstnode not in all_routes_to_try:
            continue
        for srcnode in srcnodes:
            if srcnode.startswith("IO_DATAIN") or srcnode.startswith("LE_BUFFER"):
                continue
            # print(dstnode, srcnode)
            assert all_routes_to_try[dstnode][srcnode] != False
            all_routes_to_try[dstnode][srcnode] = True

    # print(all_routes_to_try)
    with open(outfn, 'w') as f:
        json.dump(all_routes_to_try, f, sort_keys=True, indent=4, separators=(',', ': '))

def prep_all_routes_lab(outfn, my_wire_to_quartus_wire):
    all_routes_to_try = {}

    for labX in range(2, 8):
        for labY in range(1, 5):
            # Inputs to LAB
            for II in range(26):
                li_inputs = {}
                equivX = labX + (1 if II in range(0, 5) or II in range(13, 18) else 0)

                # All up wires below this
                for srcY in range(1, labY + 1):
                    for srcI in range(7):
                        li_inputs["U:X{}Y{}I{}".format(equivX, srcY, srcI)] = "maybe"
                # "Left" part of the bottom IOs in this column
                if equivX != 8:
                    for srcI in range(5):
                        li_inputs["U:X{}Y0I{}".format(equivX, srcI)] = "maybe"
                # "Right" part of the bottom IOs in the column to the left
                if equivX != 2:
                    for srcI in range(5):
                        li_inputs["U:X{}Y0I{}".format(equivX - 1, srcI + 5)] = "maybe"

                # All down wires above this
                for srcY in range(labY, 5):
                    for srcI in range(7):
                        li_inputs["D:X{}Y{}I{}".format(equivX, srcY, srcI)] = "maybe"
                # "Left" part of the top IOs in this column
                if equivX != 8:
                    for srcI in range(5):
                        li_inputs["D:X{}Y5I{}".format(equivX, srcI)] = "maybe"
                # "Right" part of the top IOs in the column to the left
                if equivX != 2:
                    for srcI in range(5):
                        li_inputs["D:X{}Y5I{}".format(equivX - 1, srcI + 5)] = "maybe"

                # All right wires to the left of this (including IOs)
                for srcX in range(1, min(8, labX + 2)):
                    for srcI in range(8):
                        li_inputs["R:X{}Y{}I{}".format(srcX, labY, srcI)] = "maybe"

                # All left wires to the right of this (IOs not fully understood)
                for srcX in range(max(3, labX), 9):
                    for srcI in range(8):
                        li_inputs["L:X{}Y{}I{}".format(srcX, labY, srcI)] = "maybe"
                for srcI in range(8):
                    li_inputs["L2:X8Y{}I{}".format(labY, srcI)] = "maybe"

                all_routes_to_try["LOCAL_INTERCONNECT:X{}Y{}S0I{}".format(labX, labY, II)] = li_inputs

            # Outputs from LAB
            for II in range(20):
                # Right wires (this and the one to the left)
                for dstI in range(8):
                    dstwire = "R:X{}Y{}I{}".format(labX, labY, dstI)
                    if dstwire not in all_routes_to_try:
                        all_routes_to_try[dstwire] = {}
                    all_routes_to_try[dstwire]["LE_BUFFER:X{}Y{}S0I{}".format(labX, labY, II)] = "maybe"
                if labX !=  2:
                    for dstI in range(8):
                        dstwire = "R:X{}Y{}I{}".format(labX - 1, labY, dstI)
                        if dstwire not in all_routes_to_try:
                            all_routes_to_try[dstwire] = {}
                        all_routes_to_try[dstwire]["LE_BUFFER:X{}Y{}S0I{}".format(labX, labY, II)] = "maybe"

                # Left wires (this and the one to the right)
                if labX != 2:
                    for dstI in range(8):
                        dstwire = "L:X{}Y{}I{}".format(labX, labY, dstI)
                        if dstwire not in all_routes_to_try:
                            all_routes_to_try[dstwire] = {}
                        all_routes_to_try[dstwire]["LE_BUFFER:X{}Y{}S0I{}".format(labX, labY, II)] = "maybe"
                for dstI in range(8):
                    dstwire = "L:X{}Y{}I{}".format(labX + 1, labY, dstI)
                    if dstwire not in all_routes_to_try:
                        all_routes_to_try[dstwire] = {}
                    all_routes_to_try[dstwire]["LE_BUFFER:X{}Y{}S0I{}".format(labX, labY, II)] = "maybe"
                if labX == 7:
                    for dstI in range(8):
                        dstwire = "L2:X{}Y{}I{}".format(labX + 1, labY, dstI)
                        if dstwire not in all_routes_to_try:
                            all_routes_to_try[dstwire] = {}
                        all_routes_to_try[dstwire]["LE_BUFFER:X{}Y{}S0I{}".format(labX, labY, II)] = "maybe"

                # Up wires (this and the one to the right)
                for dstI in range(7):
                    dstwire = "U:X{}Y{}I{}".format(labX, labY, dstI)
                    if dstwire not in all_routes_to_try:
                        all_routes_to_try[dstwire] = {}
                    all_routes_to_try[dstwire]["LE_BUFFER:X{}Y{}S0I{}".format(labX, labY, II)] = "maybe"
                for dstI in range(7):
                    dstwire = "U:X{}Y{}I{}".format(labX + 1, labY, dstI)
                    if dstwire not in all_routes_to_try:
                        all_routes_to_try[dstwire] = {}
                    all_routes_to_try[dstwire]["LE_BUFFER:X{}Y{}S0I{}".format(labX, labY, II)] = "maybe"

                # Down wires (this and the one to the right)
                for dstI in range(7):
                    dstwire = "D:X{}Y{}I{}".format(labX, labY, dstI)
                    if dstwire not in all_routes_to_try:
                        all_routes_to_try[dstwire] = {}
                    all_routes_to_try[dstwire]["LE_BUFFER:X{}Y{}S0I{}".format(labX, labY, II)] = "maybe"
                for dstI in range(7):
                    dstwire = "D:X{}Y{}I{}".format(labX + 1, labY, dstI)
                    if dstwire not in all_routes_to_try:
                        all_routes_to_try[dstwire] = {}
                    all_routes_to_try[dstwire]["LE_BUFFER:X{}Y{}S0I{}".format(labX, labY, II)] = "maybe"

    for k, v in all_routes_to_try.items():
        if k.startswith("LOCAL_INTERCONNECT"):
            continue
        if k not in my_wire_to_quartus_wire:
            print(k)
        assert k in my_wire_to_quartus_wire
        for k in v:
            if k.startswith("LE_BUFFER"):
                continue
            if k not in my_wire_to_quartus_wire:
                print(k)
            assert k in my_wire_to_quartus_wire

    # What do we already know?
    with open('initial-interconnect.json', 'r') as f:
        initial_interconnect_map = json.load(f)

    for dstnode, srcnodes in initial_interconnect_map.items():
        if dstnode not in all_routes_to_try:
            continue
        for srcnode in srcnodes:
            if srcnode.startswith("IO_DATAIN"):
                continue
            if srcnode not in all_routes_to_try[dstnode]:
                continue
            print(dstnode, srcnode)
            assert all_routes_to_try[dstnode][srcnode] != False
            all_routes_to_try[dstnode][srcnode] = True

    with open(outfn, 'w') as f:
        json.dump(all_routes_to_try, f, sort_keys=True, indent=4, separators=(',', ': '))

def prep_all_routes_lab2(outfn, my_wire_to_quartus_wire):
    all_routes_to_try = {}

    for labX in range(2, 8):
        for labY in range(1, 5):
            # Outputs from LAB
            for II in range(20):
                # Right wires (this and the one to the right)
                for dstI in range(8):
                    dstwire = "R:X{}Y{}I{}".format(labX, labY, dstI)
                    if dstwire not in all_routes_to_try:
                        all_routes_to_try[dstwire] = {}
                    all_routes_to_try[dstwire]["LE_BUFFER:X{}Y{}S0I{}".format(labX, labY, II)] = "maybe"
                if labX !=  7:
                    for dstI in range(8):
                        dstwire = "R:X{}Y{}I{}".format(labX + 1, labY, dstI)
                        if dstwire not in all_routes_to_try:
                            all_routes_to_try[dstwire] = {}
                        all_routes_to_try[dstwire]["LE_BUFFER:X{}Y{}S0I{}".format(labX, labY, II)] = "maybe"

                # Up wires (this and the one to the right)
                for dstI in range(7):
                    dstwire = "U:X{}Y{}I{}".format(labX, labY, dstI)
                    if dstwire not in all_routes_to_try:
                        all_routes_to_try[dstwire] = {}
                    all_routes_to_try[dstwire]["LE_BUFFER:X{}Y{}S0I{}".format(labX, labY, II)] = "maybe"
                for dstI in range(7):
                    dstwire = "U:X{}Y{}I{}".format(labX + 1, labY, dstI)
                    if dstwire not in all_routes_to_try:
                        all_routes_to_try[dstwire] = {}
                    all_routes_to_try[dstwire]["LE_BUFFER:X{}Y{}S0I{}".format(labX, labY, II)] = "maybe"

                # Down wires (this and the one to the right)
                for dstI in range(7):
                    dstwire = "D:X{}Y{}I{}".format(labX, labY, dstI)
                    if dstwire not in all_routes_to_try:
                        all_routes_to_try[dstwire] = {}
                    all_routes_to_try[dstwire]["LE_BUFFER:X{}Y{}S0I{}".format(labX, labY, II)] = "maybe"
                for dstI in range(7):
                    dstwire = "D:X{}Y{}I{}".format(labX + 1, labY, dstI)
                    if dstwire not in all_routes_to_try:
                        all_routes_to_try[dstwire] = {}
                    all_routes_to_try[dstwire]["LE_BUFFER:X{}Y{}S0I{}".format(labX, labY, II)] = "maybe"

                # Again for row below
                if labY != 1:
                    # Right wires (this and the one to the right)
                    for dstI in range(8):
                        dstwire = "R:X{}Y{}I{}".format(labX, labY - 1, dstI)
                        if dstwire not in all_routes_to_try:
                            all_routes_to_try[dstwire] = {}
                        all_routes_to_try[dstwire]["LE_BUFFER:X{}Y{}S0I{}".format(labX, labY, II)] = "maybe"
                    if labX !=  7:
                        for dstI in range(8):
                            dstwire = "R:X{}Y{}I{}".format(labX + 1, labY - 1, dstI)
                            if dstwire not in all_routes_to_try:
                                all_routes_to_try[dstwire] = {}
                            all_routes_to_try[dstwire]["LE_BUFFER:X{}Y{}S0I{}".format(labX, labY, II)] = "maybe"

                    # Left wires (this and the one to the right)
                    if labX != 2:
                        for dstI in range(8):
                            dstwire = "L:X{}Y{}I{}".format(labX, labY - 1, dstI)
                            if dstwire not in all_routes_to_try:
                                all_routes_to_try[dstwire] = {}
                            all_routes_to_try[dstwire]["LE_BUFFER:X{}Y{}S0I{}".format(labX, labY, II)] = "maybe"
                    for dstI in range(8):
                        dstwire = "L:X{}Y{}I{}".format(labX + 1, labY - 1, dstI)
                        if dstwire not in all_routes_to_try:
                            all_routes_to_try[dstwire] = {}
                        all_routes_to_try[dstwire]["LE_BUFFER:X{}Y{}S0I{}".format(labX, labY, II)] = "maybe"
                    if labX == 7:
                        for dstI in range(8):
                            dstwire = "L2:X{}Y{}I{}".format(labX + 1, labY - 1, dstI)
                            if dstwire not in all_routes_to_try:
                                all_routes_to_try[dstwire] = {}
                            all_routes_to_try[dstwire]["LE_BUFFER:X{}Y{}S0I{}".format(labX, labY, II)] = "maybe"

                    # Up wires (this and the one to the right)
                    for dstI in range(7):
                        dstwire = "U:X{}Y{}I{}".format(labX, labY - 1, dstI)
                        if dstwire not in all_routes_to_try:
                            all_routes_to_try[dstwire] = {}
                        all_routes_to_try[dstwire]["LE_BUFFER:X{}Y{}S0I{}".format(labX, labY, II)] = "maybe"
                    for dstI in range(7):
                        dstwire = "U:X{}Y{}I{}".format(labX + 1, labY - 1, dstI)
                        if dstwire not in all_routes_to_try:
                            all_routes_to_try[dstwire] = {}
                        all_routes_to_try[dstwire]["LE_BUFFER:X{}Y{}S0I{}".format(labX, labY, II)] = "maybe"

                    # Down wires (this and the one to the right)
                    for dstI in range(7):
                        dstwire = "D:X{}Y{}I{}".format(labX, labY - 1, dstI)
                        if dstwire not in all_routes_to_try:
                            all_routes_to_try[dstwire] = {}
                        all_routes_to_try[dstwire]["LE_BUFFER:X{}Y{}S0I{}".format(labX, labY, II)] = "maybe"
                    for dstI in range(7):
                        dstwire = "D:X{}Y{}I{}".format(labX + 1, labY - 1, dstI)
                        if dstwire not in all_routes_to_try:
                            all_routes_to_try[dstwire] = {}
                        all_routes_to_try[dstwire]["LE_BUFFER:X{}Y{}S0I{}".format(labX, labY, II)] = "maybe"

    for k, v in all_routes_to_try.items():
        if k.startswith("LOCAL_INTERCONNECT"):
            continue
        if k not in my_wire_to_quartus_wire:
            print(k)
        assert k in my_wire_to_quartus_wire
        for k in v:
            if k.startswith("LE_BUFFER"):
                continue
            if k not in my_wire_to_quartus_wire:
                print(k)
            assert k in my_wire_to_quartus_wire

    # What do we already know?
    with open('initial-interconnect.json', 'r') as f:
        initial_interconnect_map = json.load(f)

    for dstnode, srcnodes in initial_interconnect_map.items():
        if dstnode not in all_routes_to_try:
            continue
        for srcnode in srcnodes:
            if srcnode.startswith("IO_DATAIN"):
                continue
            if srcnode not in all_routes_to_try[dstnode]:
                continue
            print(dstnode, srcnode)
            assert all_routes_to_try[dstnode][srcnode] != False
            all_routes_to_try[dstnode][srcnode] = True

    with open('initial-lab-state.json', 'r') as f:
        old_lab_state = json.load(f)

    for dstnode, srcnodes in old_lab_state.items():
        if dstnode not in all_routes_to_try:
            continue
        for srcnode, works in srcnodes.items():
            if srcnode not in all_routes_to_try[dstnode]:
                continue
            print(dstnode, srcnode, works)
            if works == False:
                assert all_routes_to_try[dstnode][srcnode] != True
                all_routes_to_try[dstnode][srcnode] = False
            elif works == True:
                assert all_routes_to_try[dstnode][srcnode] == True

    with open(outfn, 'w') as f:
        json.dump(all_routes_to_try, f, sort_keys=True, indent=4, separators=(',', ': '))

def prep_all_routes_lab3(outfn, my_wire_to_quartus_wire):
    all_routes_to_try = {}

    for labX in range(2, 8):
        for labY in range(1, 5):
            # Outputs from LAB
            for II in range(20):
                # Again for row above
                if labY != 4:
                    # Right wires (this and the one to the right)
                    for dstI in range(8):
                        dstwire = "R:X{}Y{}I{}".format(labX, labY + 1, dstI)
                        if dstwire not in all_routes_to_try:
                            all_routes_to_try[dstwire] = {}
                        all_routes_to_try[dstwire]["LE_BUFFER:X{}Y{}S0I{}".format(labX, labY, II)] = "maybe"
                    if labX !=  7:
                        for dstI in range(8):
                            dstwire = "R:X{}Y{}I{}".format(labX + 1, labY + 1, dstI)
                            if dstwire not in all_routes_to_try:
                                all_routes_to_try[dstwire] = {}
                            all_routes_to_try[dstwire]["LE_BUFFER:X{}Y{}S0I{}".format(labX, labY, II)] = "maybe"

                    # Left wires (this and the one to the right)
                    if labX != 2:
                        for dstI in range(8):
                            dstwire = "L:X{}Y{}I{}".format(labX, labY + 1, dstI)
                            if dstwire not in all_routes_to_try:
                                all_routes_to_try[dstwire] = {}
                            all_routes_to_try[dstwire]["LE_BUFFER:X{}Y{}S0I{}".format(labX, labY, II)] = "maybe"
                    for dstI in range(8):
                        dstwire = "L:X{}Y{}I{}".format(labX + 1, labY + 1, dstI)
                        if dstwire not in all_routes_to_try:
                            all_routes_to_try[dstwire] = {}
                        all_routes_to_try[dstwire]["LE_BUFFER:X{}Y{}S0I{}".format(labX, labY, II)] = "maybe"
                    if labX == 7:
                        for dstI in range(8):
                            dstwire = "L2:X{}Y{}I{}".format(labX + 1, labY + 1, dstI)
                            if dstwire not in all_routes_to_try:
                                all_routes_to_try[dstwire] = {}
                            all_routes_to_try[dstwire]["LE_BUFFER:X{}Y{}S0I{}".format(labX, labY, II)] = "maybe"

                    # Up wires (this and the one to the right)
                    for dstI in range(7):
                        dstwire = "U:X{}Y{}I{}".format(labX, labY + 1, dstI)
                        if dstwire not in all_routes_to_try:
                            all_routes_to_try[dstwire] = {}
                        all_routes_to_try[dstwire]["LE_BUFFER:X{}Y{}S0I{}".format(labX, labY, II)] = "maybe"
                    for dstI in range(7):
                        dstwire = "U:X{}Y{}I{}".format(labX + 1, labY + 1, dstI)
                        if dstwire not in all_routes_to_try:
                            all_routes_to_try[dstwire] = {}
                        all_routes_to_try[dstwire]["LE_BUFFER:X{}Y{}S0I{}".format(labX, labY, II)] = "maybe"

                    # Down wires (this and the one to the right)
                    for dstI in range(7):
                        dstwire = "D:X{}Y{}I{}".format(labX, labY + 1, dstI)
                        if dstwire not in all_routes_to_try:
                            all_routes_to_try[dstwire] = {}
                        all_routes_to_try[dstwire]["LE_BUFFER:X{}Y{}S0I{}".format(labX, labY, II)] = "maybe"
                    for dstI in range(7):
                        dstwire = "D:X{}Y{}I{}".format(labX + 1, labY + 1, dstI)
                        if dstwire not in all_routes_to_try:
                            all_routes_to_try[dstwire] = {}
                        all_routes_to_try[dstwire]["LE_BUFFER:X{}Y{}S0I{}".format(labX, labY, II)] = "maybe"

    for k, v in all_routes_to_try.items():
        if k.startswith("LOCAL_INTERCONNECT"):
            continue
        if k not in my_wire_to_quartus_wire:
            print(k)
        assert k in my_wire_to_quartus_wire
        for k in v:
            if k.startswith("LE_BUFFER"):
                continue
            if k not in my_wire_to_quartus_wire:
                print(k)
            assert k in my_wire_to_quartus_wire

    # What do we already know?
    with open('initial-interconnect.json', 'r') as f:
        initial_interconnect_map = json.load(f)

    for dstnode, srcnodes in initial_interconnect_map.items():
        if dstnode not in all_routes_to_try:
            continue
        for srcnode in srcnodes:
            if srcnode.startswith("IO_DATAIN"):
                continue
            if srcnode not in all_routes_to_try[dstnode]:
                continue
            print(dstnode, srcnode)
            assert all_routes_to_try[dstnode][srcnode] != False
            all_routes_to_try[dstnode][srcnode] = True

    with open('initial-lab-state.json', 'r') as f:
        old_lab_state = json.load(f)

    for dstnode, srcnodes in old_lab_state.items():
        if dstnode not in all_routes_to_try:
            continue
        for srcnode, works in srcnodes.items():
            if srcnode not in all_routes_to_try[dstnode]:
                continue
            print(dstnode, srcnode, works)
            if works == False:
                assert all_routes_to_try[dstnode][srcnode] != True
                all_routes_to_try[dstnode][srcnode] = False
            elif works == True:
                assert all_routes_to_try[dstnode][srcnode] == True

    with open('initial-lab2-state.json', 'r') as f:
        old_lab_state = json.load(f)

    for dstnode, srcnodes in old_lab_state.items():
        if dstnode not in all_routes_to_try:
            continue
        for srcnode, works in srcnodes.items():
            if srcnode not in all_routes_to_try[dstnode]:
                continue
            print(dstnode, srcnode, works)
            if works == False:
                assert all_routes_to_try[dstnode][srcnode] != True
                all_routes_to_try[dstnode][srcnode] = False
            elif works == True:
                assert all_routes_to_try[dstnode][srcnode] == True

    with open(outfn, 'w') as f:
        json.dump(all_routes_to_try, f, sort_keys=True, indent=4, separators=(',', ': '))

def prep_all_routes_ioout(outfn, my_wire_to_quartus_wire):
    all_routes_to_try = {}

    for ioX in [1, 8]:
        for ioY in range(1, 5):
            # IO indices
            if ioX == 1 or ioY == 2:
                N = 4
            else:
                N = 5

            if ioX == 1:
                udX = 2
            else:
                udX = 8

            for ioI in range(N):
                # Right wires
                if ioX == 1:
                    for dstI in range(8):
                        dstwire = "R:X{}Y{}I{}".format(ioX + 1, ioY, dstI)
                        if dstwire not in all_routes_to_try:
                            all_routes_to_try[dstwire] = {}
                        all_routes_to_try[dstwire]["IO_DATAIN:X{}Y{}S{}I0".format(ioX, ioY, ioI)] = "maybe"

                # Left wires
                if ioX == 8:
                    for dstI in range(8):
                        dstwire = "L:X{}Y{}I{}".format(ioX, ioY, dstI)
                        if dstwire not in all_routes_to_try:
                            all_routes_to_try[dstwire] = {}
                        all_routes_to_try[dstwire]["IO_DATAIN:X{}Y{}S{}I0".format(ioX, ioY, ioI)] = "maybe"
                    for dstI in range(8):
                        dstwire = "L2:X{}Y{}I{}".format(ioX, ioY, dstI)
                        if dstwire not in all_routes_to_try:
                            all_routes_to_try[dstwire] = {}
                        all_routes_to_try[dstwire]["IO_DATAIN:X{}Y{}S{}I0".format(ioX, ioY, ioI)] = "maybe"

                # Up wires
                for dstI in range(7):
                    dstwire = "U:X{}Y{}I{}".format(udX, ioY, dstI)
                    if dstwire not in all_routes_to_try:
                        all_routes_to_try[dstwire] = {}
                    all_routes_to_try[dstwire]["IO_DATAIN:X{}Y{}S{}I0".format(ioX, ioY, ioI)] = "maybe"

                # Down wires
                for dstI in range(7):
                    dstwire = "D:X{}Y{}I{}".format(udX, ioY, dstI)
                    if dstwire not in all_routes_to_try:
                        all_routes_to_try[dstwire] = {}
                    all_routes_to_try[dstwire]["IO_DATAIN:X{}Y{}S{}I0".format(ioX, ioY, ioI)] = "maybe"

                # Again for row below
                if ioY != 1:
                    # Right wires
                    if ioX == 1:
                        for dstI in range(8):
                            dstwire = "R:X{}Y{}I{}".format(ioX + 1, ioY - 1, dstI)
                            if dstwire not in all_routes_to_try:
                                all_routes_to_try[dstwire] = {}
                            all_routes_to_try[dstwire]["IO_DATAIN:X{}Y{}S{}I0".format(ioX, ioY, ioI)] = "maybe"

                    # Left wires
                    if ioX == 8:
                        for dstI in range(8):
                            dstwire = "L:X{}Y{}I{}".format(ioX, ioY - 1, dstI)
                            if dstwire not in all_routes_to_try:
                                all_routes_to_try[dstwire] = {}
                            all_routes_to_try[dstwire]["IO_DATAIN:X{}Y{}S{}I0".format(ioX, ioY, ioI)] = "maybe"
                        for dstI in range(8):
                            dstwire = "L2:X{}Y{}I{}".format(ioX, ioY, dstI)
                            if dstwire not in all_routes_to_try:
                                all_routes_to_try[dstwire] = {}
                            all_routes_to_try[dstwire]["IO_DATAIN:X{}Y{}S{}I0".format(ioX, ioY, ioI)] = "maybe"

                    # Up wires
                    for dstI in range(7):
                        dstwire = "U:X{}Y{}I{}".format(udX, ioY - 1, dstI)
                        if dstwire not in all_routes_to_try:
                            all_routes_to_try[dstwire] = {}
                        all_routes_to_try[dstwire]["IO_DATAIN:X{}Y{}S{}I0".format(ioX, ioY, ioI)] = "maybe"

                    # Down wires
                    for dstI in range(7):
                        dstwire = "D:X{}Y{}I{}".format(udX, ioY - 1, dstI)
                        if dstwire not in all_routes_to_try:
                            all_routes_to_try[dstwire] = {}
                        all_routes_to_try[dstwire]["IO_DATAIN:X{}Y{}S{}I0".format(ioX, ioY, ioI)] = "maybe"

                # Again for row again
                if ioY != 4:
                    # Right wires
                    if ioX == 1:
                        for dstI in range(8):
                            dstwire = "R:X{}Y{}I{}".format(ioX + 1, ioY + 1, dstI)
                            if dstwire not in all_routes_to_try:
                                all_routes_to_try[dstwire] = {}
                            all_routes_to_try[dstwire]["IO_DATAIN:X{}Y{}S{}I0".format(ioX, ioY, ioI)] = "maybe"

                    # Left wires
                    if ioX == 8:
                        for dstI in range(8):
                            dstwire = "L:X{}Y{}I{}".format(ioX, ioY + 1, dstI)
                            if dstwire not in all_routes_to_try:
                                all_routes_to_try[dstwire] = {}
                            all_routes_to_try[dstwire]["IO_DATAIN:X{}Y{}S{}I0".format(ioX, ioY, ioI)] = "maybe"
                        for dstI in range(8):
                            dstwire = "L2:X{}Y{}I{}".format(ioX, ioY, dstI)
                            if dstwire not in all_routes_to_try:
                                all_routes_to_try[dstwire] = {}
                            all_routes_to_try[dstwire]["IO_DATAIN:X{}Y{}S{}I0".format(ioX, ioY, ioI)] = "maybe"

                    # Up wires
                    for dstI in range(7):
                        dstwire = "U:X{}Y{}I{}".format(udX, ioY + 1, dstI)
                        if dstwire not in all_routes_to_try:
                            all_routes_to_try[dstwire] = {}
                        all_routes_to_try[dstwire]["IO_DATAIN:X{}Y{}S{}I0".format(ioX, ioY, ioI)] = "maybe"

                    # Down wires
                    for dstI in range(7):
                        dstwire = "D:X{}Y{}I{}".format(udX, ioY + 1, dstI)
                        if dstwire not in all_routes_to_try:
                            all_routes_to_try[dstwire] = {}
                        all_routes_to_try[dstwire]["IO_DATAIN:X{}Y{}S{}I0".format(ioX, ioY, ioI)] = "maybe"

    for k, v in all_routes_to_try.items():
        if k.startswith("LOCAL_INTERCONNECT"):
            continue
        if k not in my_wire_to_quartus_wire:
            print(k)
        assert k in my_wire_to_quartus_wire
        for k in v:
            if k.startswith("IO_DATAIN"):
                continue
            if k not in my_wire_to_quartus_wire:
                print(k)
            assert k in my_wire_to_quartus_wire

    # What do we already know?
    with open('initial-interconnect.json', 'r') as f:
        initial_interconnect_map = json.load(f)

    for dstnode, srcnodes in initial_interconnect_map.items():
        if dstnode not in all_routes_to_try:
            continue
        for srcnode in srcnodes:
            if srcnode not in all_routes_to_try[dstnode]:
                continue
            print(dstnode, srcnode)
            assert all_routes_to_try[dstnode][srcnode] != False
            all_routes_to_try[dstnode][srcnode] = True

    with open(outfn, 'w') as f:
        json.dump(all_routes_to_try, f, sort_keys=True, indent=4, separators=(',', ': '))

def update_state(old_state_fn, new_interconnect_fn, outfn):
    with open(old_state_fn, 'r') as f:
        all_routes_to_try = json.load(f)
    with open(new_interconnect_fn, 'r') as f:
        initial_interconnect_map = json.load(f)

    # Remove self-routes lol
    for dst, srcs in all_routes_to_try.items():
        if dst in srcs:
            assert srcs[dst] != True
            del srcs[dst]

    for dstnode, srcnodes in initial_interconnect_map.items():
        if dstnode not in all_routes_to_try:
            continue
        for srcnode in srcnodes:
            if srcnode.startswith("IO_DATAIN"):
                continue
            if srcnode not in all_routes_to_try[dstnode]:
                continue
            # print(dstnode, srcnode)
            assert all_routes_to_try[dstnode][srcnode] != False
            all_routes_to_try[dstnode][srcnode] = True

    # print(all_routes_to_try)
    with open(outfn, 'w') as f:
        json.dump(all_routes_to_try, f, sort_keys=True, indent=4, separators=(',', ': '))

def parse_xysi2(inp):
    xpos = inp.find('X')
    ypos = inp.find('Y')
    spos = inp.find('S')
    ipos = inp.find('I')

    assert xpos >= 0
    assert ypos > xpos
    assert spos > ypos
    assert ipos > spos

    return (int(inp[xpos + 1:ypos]), int(inp[ypos + 1:spos]), int(inp[spos + 1:ipos]), int(inp[ipos + 1:]))

def route_to_output(routing_graph_srcs_dsts, node, extra_closed_nodes=[]):
    fringe = []
    closed_set = set()

    closed_set |= set(extra_closed_nodes)

    fringe.append((node, []))

    while len(fringe) > 0:
        work_node, cur_path = fringe[0]
        del fringe[0]

        # Is this an output?
        is_an_output = False
        if work_node.startswith("LOCAL_INTERCONNECT"):
            X, Y, I = parse_xysi(work_node[19:])
            if (X == 1 or X == 8):
                assert Y in range(1, 5)
                assert I in range(18)
                is_an_output = True
            elif (Y == 0 or Y == 5):
                assert X in range(2, 8)
                assert I in range(10)
                is_an_output = True
            else:
                # It's not a local interconnect we care about right now (goes to LUT)
                continue

        if is_an_output:
            return cur_path + [work_node]

        # Not an output
        if work_node in routing_graph_srcs_dsts:
            for dst in routing_graph_srcs_dsts[work_node]:
                if dst not in closed_set:
                    fringe.append((dst, cur_path + [work_node]))

                closed_set.add(dst)

    return None

def route_to_input(routing_graph_dsts_srcs, node, extra_closed_nodes=[]):
    fringe = []
    closed_set = set()

    closed_set |= set(extra_closed_nodes)

    fringe.append((node, []))

    while len(fringe) > 0:
        work_node, cur_path = fringe[0]
        del fringe[0]

        # Is this an input?
        is_an_input = False
        if work_node.startswith("LE_BUFFER"):
            continue
        elif work_node.startswith("IO_DATAIN"):
            is_an_input = True
        elif work_node.startswith("R:"):
            X, _, _ = parse_xyi(work_node)
            if X == 1:
                is_an_input = True
        elif work_node.startswith("D:"):
            _, Y, _ = parse_xyi(work_node)
            if Y == 5:
                is_an_input = True
        elif work_node.startswith("U:"):
            _, Y, _ = parse_xyi(work_node)
            if Y == 0:
                is_an_input = True

        if is_an_input:
            return cur_path + [work_node]

        # Not an input
        if work_node in routing_graph_dsts_srcs:
            for src in routing_graph_dsts_srcs[work_node]:
                if src not in closed_set:
                    fringe.append((src, cur_path + [work_node]))

                closed_set.add(src)

    return None

LEFT_MAX_IOS = [4, 4, 4, 4]
RIGHT_MAX_IOS = [5, 4, 5, 5]
TOP_MAX_IOS = [3, 4, 3, 4, 4, 4]
BOT_MAX_IOS = [4, 4, 3, 4, 4, 3]

def inp_to_io(inpname):
    if inpname.startswith("R:"):
        X, Y, I = parse_xyi(inpname)
        assert X == 1
        assert Y in range(1, 5)
        if I == 0 or I == 1 or I == 4 or I == 5:
            newI = 2
        elif I == 2 or I == 3:
            newI = 0
        elif I == 6 or I == 7:
            newI = 1
        else:
            raise Exception()
        return "IOC_X{}_Y{}_N{}".format(X, Y, newI)
    elif inpname.startswith("U:"):
        X, Y, I = parse_xyi(inpname)
        assert Y == 0
        assert X in range(2, 8)
        if (I % 5) == 0 or (I % 5) == 2 or (I % 5) == 4:
            newI = 0
        elif (I % 5) == 1:
            newI = 1
        elif (I % 5) == 3:
            newI = 2
        else:
            raise Exception()
        return "IOC_X{}_Y{}_N{}".format(X, Y, newI)
    elif inpname.startswith("D:"):
        X, Y, I = parse_xyi(inpname)
        assert Y == 5
        assert X in range(2, 8)
        if (I % 5) == 0 or (I % 5) == 2 or (I % 5) == 4:
            newI = 0
        elif (I % 5) == 3:
            newI = 1
        elif (I % 5) == 1:
            newI = 2
        else:
            raise Exception()
        return "IOC_X{}_Y{}_N{}".format(X, Y, newI)
    elif inpname.startswith("IO_DATAIN:"):
        X, Y, S, I = parse_xysi2(inpname[10:])
        assert I == 0
        assert X == 8 or X == 1
        assert Y in range(1, 5)
        if X == 8:
            assert S < RIGHT_MAX_IOS[Y - 1]
        else:
            assert S < LEFT_MAX_IOS[Y - 1]
        return "IOC_X{}_Y{}_N{}".format(X, Y, S)
    else:
        raise Exception()

def inp_to_io2(inpname):
    if inpname.startswith("R:"):
        X, Y, I = parse_xyi(inpname)
        assert X == 1
        assert Y in range(1, 5)
        if I == 0 or I == 1:
            newI_1 = 2
            newI_2 = 3
        elif I == 2 or I == 3:
            newI_1 = 0
            newI_2 = None
        elif I == 4 or I == 5:
            newI_1 = 2
            newI_2 = None
        elif I == 6 or I == 7:
            newI_1 = 1
            newI_2 = None
        else:
            raise Exception()
        if newI_2 is None:
            return ["IOC_X{}_Y{}_N{}".format(X, Y, newI_1)]
        return ["IOC_X{}_Y{}_N{}".format(X, Y, newI_1), "IOC_X{}_Y{}_N{}".format(X, Y, newI_2)]
    elif inpname.startswith("U:"):
        X, Y, I = parse_xyi(inpname)
        assert Y == 0
        assert X in range(2, 8)
        if (I % 5) == 0 or (I % 5) == 2 or (I % 5) == 4:
            newI_1 = 0
        elif (I % 5) == 1:
            newI_1 = 1
        elif (I % 5) == 3:
            newI_1 = 2
        else:
            raise Exception()
        if (I % 5) == 0 or (I % 5) == 1 or (I % 5) == 3:
            newI_2 = 3
        elif (I % 5) == 2:
            newI_2 = 2
        elif (I % 5) == 4:
            newI_2 = 1
        else:
            raise Exception()

        if X == 4 or X == 7:
            if newI_2 == 3:
                newI_2 = None

        if newI_2 is None:
            return ["IOC_X{}_Y{}_N{}".format(X, Y, newI_1)]
        return ["IOC_X{}_Y{}_N{}".format(X, Y, newI_1), "IOC_X{}_Y{}_N{}".format(X, Y, newI_2)]
    elif inpname.startswith("D:"):
        X, Y, I = parse_xyi(inpname)
        assert Y == 5
        assert X in range(2, 8)
        if (I % 5) == 0 or (I % 5) == 2 or (I % 5) == 4:
            newI_1 = 0
        elif (I % 5) == 3:
            newI_1 = 1
        elif (I % 5) == 1:
            newI_1 = 2
        else:
            raise Exception()
        if (I % 5) == 4 or (I % 5) == 3 or (I % 5) == 1:
            newI_2 = 3
        elif (I % 5) == 2:
            newI_2 = 2
        elif (I % 5) == 0:
            newI_2 = 1
        else:
            raise Exception()

        if X == 4 or X == 2:
            if newI_2 == 3:
                newI_2 = None

        if newI_2 is None:
            return ["IOC_X{}_Y{}_N{}".format(X, Y, newI_1)]
        return ["IOC_X{}_Y{}_N{}".format(X, Y, newI_1), "IOC_X{}_Y{}_N{}".format(X, Y, newI_2)]
    elif inpname.startswith("IO_DATAIN:"):
        X, Y, S, I = parse_xysi2(inpname[10:])
        assert I == 0
        assert X == 8 or X == 1
        assert Y in range(1, 5)
        if X == 8:
            assert S < RIGHT_MAX_IOS[Y - 1]
        else:
            assert S < LEFT_MAX_IOS[Y - 1]
        return ["IOC_X{}_Y{}_N{}".format(X, Y, S)]
    else:
        raise Exception()

BASE_DIR = '/home/rqou/.local/share/lxc/altera-quartus-prime-lite-18/rootfs/home/rqou'

QSF_TMPL = """set_global_assignment -name FAMILY "MAX V"
set_global_assignment -name DEVICE 5M240ZT100C4
set_global_assignment -name TOP_LEVEL_ENTITY maxvtest
set_global_assignment -name ORIGINAL_QUARTUS_VERSION 18.0.0
set_global_assignment -name PROJECT_CREATION_TIME_DATE "03:45:37  MAY 30, 2018"
set_global_assignment -name LAST_QUARTUS_VERSION "18.0.0 Lite Edition"
set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files
set_global_assignment -name ERROR_CHECK_FREQUENCY_DIVISOR "-1"
set_global_assignment -name EDA_SIMULATION_TOOL "ModelSim-Altera (Verilog)"
set_global_assignment -name EDA_TIME_SCALE "1 ps" -section_id eda_simulation
set_global_assignment -name EDA_OUTPUT_DATA_FORMAT "VERILOG HDL" -section_id eda_simulation
set_global_assignment -name VERILOG_FILE top.v
set_location_assignment {} -to a
set_location_assignment {} -to o
set_global_assignment -name ROUTING_BACK_ANNOTATION_FILE maxvtest.rcf
set_global_assignment -name NUM_PARALLEL_PROCESSORS 1
"""

NTHREADS = 30

def fuzz_a_route(workdir, vmdir, path, inp, outp, my_wire_to_quartus_wire, srcname, dstname):
    with open(workdir + '/maxvtest.qsf', 'w') as f:
        f.write(QSF_TMPL.format(inp, outp))

    with open(workdir + '/maxvtest.rcf', 'w') as f:
        f.write("signal_name = a {\n")
        f.write("    zero_or_more, *;\n")
        for pathelem in path:
            if pathelem in my_wire_to_quartus_wire:
                pathelem = my_wire_to_quartus_wire[pathelem]
            f.write("    {};\n".format(pathelem))
        f.write("    zero_or_more, *;\n")
        f.write("    dest = ( o, DATAIN );\n")
        f.write("}\n")

    while True:
        try:
            run_one_flow(vmdir, False, True, False)
            break
        except Exception:
            pass

    success = True
    with open(workdir + '/output_files/maxvtest.fit.rpt', 'r') as f:
        rptdata = f.read()
        if "Cannot route signal \"a\" to atom \"o\"" in rptdata:
            success = False
        assert "multiple usages of a single routing resource" not in rptdata

    if success:
        shutil.copy(workdir + '/output_files/maxvtest.fit.rpt', 'ioout-full-fuzz/from_{}_to_{}.fit.rpt'.format(srcname, dstname))
        shutil.copy(workdir + '/output_files/maxvtest.pof', 'ioout-full-fuzz/from_{}_to_{}.pof'.format(srcname, dstname))
        shutil.copy(workdir + '/maxvtest.rcf', 'ioout-full-fuzz/from_{}_to_{}.rcf'.format(srcname, dstname))

    return success

def threadfn(workqueue, donequeue, my_wire_to_quartus_wire, threadi):
    MYDIR = BASE_DIR + '/r4c4-full-fuzz/thread{}'.format(threadi)
    VMDIR = "r4c4-full-fuzz/thread{}".format(threadi)
    shutil.copytree(BASE_DIR + '/route-fuzz-seed', MYDIR)

    while True:
        try:
            x = workqueue.get()
            if x is None:
                donequeue.put(None)
                continue
            path, inp, outp, srcname, dstname = x
        except queue.Empty:
            continue

        success = fuzz_a_route(MYDIR, VMDIR, path, inp, outp, my_wire_to_quartus_wire, srcname, dstname)
        donequeue.put((srcname, dstname, success))

def do_fuzz(inp_state_fn, inp_route_fn, my_wire_to_quartus_wire):
    os.mkdir(BASE_DIR + '/r4c4-full-fuzz')

    with open(inp_state_fn, 'r') as f:
        fuzzing_state = json.load(f)
    with open(inp_route_fn, 'r') as f:
        # Index first by dst, then by src
        # Lists ways to get _onto_ a wire
        routing_graph_dsts_srcs = json.load(f)

    # print(routing_graph_dsts_srcs)

    # Invert the routing graph
    routing_graph_srcs_dsts = {}
    for dst, srcs in routing_graph_dsts_srcs.items():
        for src in srcs:
            # print(dst, src)
            if src not in routing_graph_srcs_dsts:
                routing_graph_srcs_dsts[src] = {dst}
            else:
                routing_graph_srcs_dsts[src].add(dst)

    # print(routing_graph_srcs_dsts)
    with open("debug-invert-graph.json", 'w') as f:
        json.dump({k: list(v) for k, v in routing_graph_srcs_dsts.items()}, f, sort_keys=True, indent=4, separators=(',', ': '))

    with open("work-r4c4-state.json", 'w') as f:
        json.dump(fuzzing_state, f, sort_keys=True, indent=4, separators=(',', ': '))
    with open("work-interconnect.json", 'w') as f:
        json.dump(routing_graph_dsts_srcs, f, sort_keys=True, indent=4, separators=(',', ': '))

    # print(route_to_output(routing_graph_srcs_dsts, "LOCAL_INTERCONNECT:X2Y0S0I9"))
    # print(route_to_output(routing_graph_srcs_dsts, "D:X2Y1I0"))
    # print(route_to_output(routing_graph_srcs_dsts, "L:X3Y1I0"))

    # print(route_to_input(routing_graph_dsts_srcs, "R:X1Y1I0"))
    # print(route_to_input(routing_graph_dsts_srcs, "R:X4Y1I1"))
    # print(route_to_input(routing_graph_dsts_srcs, "U:X8Y1I3"))
    # print(route_to_input(routing_graph_dsts_srcs, "U:X8Y1I3", ["R:X4Y1I1"]))

    # For stats, and a cache
    num_worked = 0
    num_failed = 0
    num_maybe = 0
    maybe_pairs_to_test = set()
    for dst, srcs in fuzzing_state.items():
        for src, state in srcs.items():
            if state == True:
                num_worked += 1
            elif state == False:
                num_failed += 1
            elif state == "maybe":
                num_maybe += 1
                maybe_pairs_to_test.add((src, dst))
            else:
                raise Exception()

    # print(maybe_pairs_to_test)

    workqueue = queue.Queue(2 * NTHREADS)
    # workqueue = queue.Queue()
    donequeue = queue.Queue()

    # # HACK
    # for _ in range(2 * NTHREADS):
    #     workqueue.put(None)

    last_save_time = time.time()
    outstanding_tests = set()

    for threadi in range(NTHREADS):
        t = threading.Thread(target=threadfn, args=(workqueue, donequeue, my_wire_to_quartus_wire, threadi))
        t.start()

    while len(maybe_pairs_to_test):
        while True:
            try:
                doneitem = donequeue.get(block=False)
            except queue.Empty:
                break

            if doneitem is not None:
                donesrc, donedst, donesuccess = doneitem
                print("{} -> {} ==> {}".format(donesrc, donedst, donesuccess))

                outstanding_tests.remove((donesrc, donedst))
                if (donesrc, donedst) in maybe_pairs_to_test:
                    maybe_pairs_to_test.remove((donesrc, donedst))
                else:
                    print("BUG", donesrc, donedst)
                num_maybe -= 1
                fuzzing_state[donedst][donesrc] = donesuccess
                if donesuccess:
                    num_worked += 1
                    if donedst not in routing_graph_dsts_srcs:
                        routing_graph_dsts_srcs[donedst] = {donesrc: "TODO"}
                    else:
                        routing_graph_dsts_srcs[donedst][donesrc] = "TODO"
                    if donesrc not in routing_graph_srcs_dsts:
                        routing_graph_srcs_dsts[donesrc] = set([donedst])
                    else:
                        routing_graph_srcs_dsts[donesrc].add(donedst)
                else:
                    num_failed += 1

        if (time.time() - last_save_time >= 5) or (len(maybe_pairs_to_test) == 0):
            os.remove('work-r4c4-state.json.bak')
            os.remove('work-interconnect.json.bak')
            shutil.move('work-r4c4-state.json', 'work-r4c4-state.json.bak')
            shutil.move('work-interconnect.json', 'work-interconnect.json.bak')

            with open("work-r4c4-state.json", 'w') as f:
                json.dump(fuzzing_state, f, sort_keys=True, indent=4, separators=(',', ': '))
            with open("work-interconnect.json", 'w') as f:
                json.dump(routing_graph_dsts_srcs, f, sort_keys=True, indent=4, separators=(',', ': '))

            last_save_time = time.time()

        print("Currently, there are {} routes that worked, {} routes that failed, {} routes unknown".format(num_worked, num_failed, num_maybe))

        if len(maybe_pairs_to_test) == 0:
            break

        src, dst = random.choice(tuple(maybe_pairs_to_test))

        if (src, dst) in outstanding_tests:
            continue
        outstanding_tests.add((src, dst))

        # TEST TEST TEST
        # maybe_pairs_to_test.remove((src, dst))
        # num_maybe -= 1

        dst_to_out_path = route_to_output(routing_graph_srcs_dsts, dst)
        if dst_to_out_path is None:
            # workqueue.put(None)     # HACK
            continue
        src_to_in_path = route_to_input(routing_graph_dsts_srcs, src, dst_to_out_path)
        if src_to_in_path is None:
            # workqueue.put(None)     # HACK
            continue
        if dst in src_to_in_path:
            # workqueue.put(None)     # HACK
            continue
        if src in dst_to_out_path:
            # workqueue.put(None)     # HACK
            continue
        if len(set(dst_to_out_path) & set(src_to_in_path)) != 0:
            print("BUG!", dst_to_out_path, src_to_in_path)
            # workqueue.put(None)     # HACK
            continue
        src_to_in_path = src_to_in_path[::-1]
        # print(src_to_in_path, dst_to_out_path)

        io_for_inp = inp_to_io(src_to_in_path[0])

        outp_local_int = dst_to_out_path[-1]
        assert outp_local_int.startswith("LOCAL_INTERCONNECT")
        outpX, outpY, _ = parse_xysi(outp_local_int[19:])
        io_for_outp = "IOC_X{}_Y{}_N{}".format(outpX, outpY, 0)
        if io_for_outp == io_for_inp:
            io_for_outp = "IOC_X{}_Y{}_N{}".format(outpX, outpY, 1)
        assert io_for_outp != io_for_inp

        # print(io_for_inp, io_for_outp)

        # route_was_ok = fuzz_a_route(MYDIR, src_to_in_path + dst_to_out_path, io_for_inp, io_for_outp, my_wire_to_quartus_wire, src, dst)

        # print(route_was_ok)
        print("Testing {} -> {}".format(src, dst))
        workqueue.put((src_to_in_path + dst_to_out_path, io_for_inp, io_for_outp, src, dst))

        # break

QSF_TMPL2 = """set_global_assignment -name FAMILY "MAX V"
set_global_assignment -name DEVICE 5M240ZT100C4
set_global_assignment -name TOP_LEVEL_ENTITY maxvtest
set_global_assignment -name ORIGINAL_QUARTUS_VERSION 18.0.0
set_global_assignment -name PROJECT_CREATION_TIME_DATE "03:45:37  MAY 30, 2018"
set_global_assignment -name LAST_QUARTUS_VERSION "18.0.0 Lite Edition"
set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files
set_global_assignment -name ERROR_CHECK_FREQUENCY_DIVISOR "-1"
set_global_assignment -name EDA_SIMULATION_TOOL "ModelSim-Altera (Verilog)"
set_global_assignment -name EDA_TIME_SCALE "1 ps" -section_id eda_simulation
set_global_assignment -name EDA_OUTPUT_DATA_FORMAT "VERILOG HDL" -section_id eda_simulation
set_global_assignment -name VERILOG_FILE top.v
set_location_assignment {} -to a
set_location_assignment {} -to b
set_location_assignment {} -to o
set_location_assignment LC_X{}_Y{}_N{} -to my_lcell
set_global_assignment -name ROUTING_BACK_ANNOTATION_FILE maxvtest.rcf
set_global_assignment -name NUM_PARALLEL_PROCESSORS 1
"""

def fuzz_a_route2(workdir, vmdir, my_wire_to_quartus_wire, pathA, pathB, pathO, inpA, inpB, outp, lutX, lutY, lutN, srcname, dstname):
    with open(workdir + '/maxvtest.qsf', 'w') as f:
        f.write(QSF_TMPL2.format(inpA, inpB, outp, lutX, lutY, lutN))

    with open(workdir + '/maxvtest.rcf', 'w') as f:
        f.write("signal_name = a {\n")
        f.write("    zero_or_more, *;\n")
        for pathelem in pathA:
            if pathelem in my_wire_to_quartus_wire:
                pathelem = my_wire_to_quartus_wire[pathelem]
            f.write("    {};\n".format(pathelem))
        f.write("    dest = ( my_lcell, DATAA );\n")
        f.write("}\n")

        f.write("signal_name = b {\n")
        f.write("    zero_or_more, *;\n")
        for pathelem in pathB:
            if pathelem in my_wire_to_quartus_wire:
                pathelem = my_wire_to_quartus_wire[pathelem]
            f.write("    {};\n".format(pathelem))
        f.write("    dest = ( my_lcell, DATAB );\n")
        f.write("}\n")

        f.write("signal_name = my_lcell {\n")
        for pathelem in pathO:
            if pathelem in my_wire_to_quartus_wire:
                pathelem = my_wire_to_quartus_wire[pathelem]
            f.write("    {};\n".format(pathelem))
        f.write("    zero_or_more, *;\n")
        f.write("    dest = ( o, DATAIN );\n")
        f.write("}\n")

    while True:
        try:
            run_one_flow(vmdir, False, True, False)
            break
        except Exception:
            pass

    success = True
    with open(workdir + '/output_files/maxvtest.fit.rpt', 'r') as f:
        rptdata = f.read()
        if "Cannot route signal " in rptdata:
            success = False
        assert "multiple usages of a single routing resource" not in rptdata

    if success:
        shutil.copy(workdir + '/output_files/maxvtest.fit.rpt', 'labr4c4-new-fuzz/from_{}_to_{}.fit.rpt'.format(srcname, dstname))
        shutil.copy(workdir + '/output_files/maxvtest.pof', 'labr4c4-new-fuzz/from_{}_to_{}.pof'.format(srcname, dstname))
        shutil.copy(workdir + '/maxvtest.rcf', 'labr4c4-new-fuzz/from_{}_to_{}.rcf'.format(srcname, dstname))

    return success

def threadfn2(workqueue, donequeue, my_wire_to_quartus_wire, threadi):
    MYDIR = BASE_DIR + '/labr4c4-full-fuzz/thread{}'.format(threadi)
    VMDIR = "labr4c4-full-fuzz/thread{}".format(threadi)
    shutil.copytree(BASE_DIR + '/labr4c4-seed', MYDIR)

    if threadi >= NTHREADS // 2:
        time.sleep(10)

    while True:
        try:
            x = workqueue.get()
            if x is None:
                donequeue.put(None)
                continue
            pathA, pathB, pathO, inpA, inpB, outp, lutX, lutY, lutN, srcname, dstname = x
        except queue.Empty:
            continue

        # print(pathA, pathB, pathO, inpA, inpB, outp, lutX, lutY, lutN, srcname, dstname)
        success = fuzz_a_route2(MYDIR, VMDIR, my_wire_to_quartus_wire, pathA, pathB, pathO, inpA, inpB, outp, lutX, lutY, lutN, srcname, dstname)
        donequeue.put((srcname, dstname, success))

def do_fuzz_lab(inp_state_fn, inp_route_fn, my_wire_to_quartus_wire):
    os.mkdir(BASE_DIR + '/labr4c4-full-fuzz')

    with open(inp_state_fn, 'r') as f:
        fuzzing_state = json.load(f)
    with open(inp_route_fn, 'r') as f:
        # Index first by dst, then by src
        # Lists ways to get _onto_ a wire
        routing_graph_dsts_srcs = json.load(f)

    # Invert the routing graph
    routing_graph_srcs_dsts = {}
    for dst, srcs in routing_graph_dsts_srcs.items():
        for src in srcs:
            if src not in routing_graph_srcs_dsts:
                routing_graph_srcs_dsts[src] = {dst}
            else:
                routing_graph_srcs_dsts[src].add(dst)

    with open("debug-invert-graph.json", 'w') as f:
        json.dump({k: list(v) for k, v in routing_graph_srcs_dsts.items()}, f, sort_keys=True, indent=4, separators=(',', ': '))

    with open("work-lab-state.json", 'w') as f:
        json.dump(fuzzing_state, f, sort_keys=True, indent=4, separators=(',', ': '))
    with open("work-interconnect.json", 'w') as f:
        json.dump(routing_graph_dsts_srcs, f, sort_keys=True, indent=4, separators=(',', ': '))

    # For stats, and a cache
    num_worked = 0
    num_failed = 0
    num_maybe = 0
    maybe_pairs_to_test = set()
    for dst, srcs in fuzzing_state.items():
        for src, state in srcs.items():
            if state == True:
                num_worked += 1
            elif state == False:
                num_failed += 1
            elif state == "maybe":
                num_maybe += 1
                maybe_pairs_to_test.add((src, dst))
            else:
                raise Exception()

    workqueue = queue.Queue(2 * NTHREADS)
    donequeue = queue.Queue()

    last_save_time = time.time()
    outstanding_tests = set()

    for threadi in range(NTHREADS):
        t = threading.Thread(target=threadfn2, args=(workqueue, donequeue, my_wire_to_quartus_wire, threadi))
        t.start()

    while len(maybe_pairs_to_test):
        while True:
            try:
                doneitem = donequeue.get(block=False)
            except queue.Empty:
                break

            if doneitem is not None:
                donesrc, donedst, donesuccess = doneitem
                print("{} -> {} ==> {}".format(donesrc, donedst, donesuccess))

                outstanding_tests.remove((donesrc, donedst))
                if (donesrc, donedst) in maybe_pairs_to_test:
                    maybe_pairs_to_test.remove((donesrc, donedst))
                else:
                    print("BUG", donesrc, donedst)
                num_maybe -= 1
                fuzzing_state[donedst][donesrc] = donesuccess
                if donesuccess:
                    num_worked += 1
                    if donedst not in routing_graph_dsts_srcs:
                        routing_graph_dsts_srcs[donedst] = {donesrc: "TODO"}
                    else:
                        routing_graph_dsts_srcs[donedst][donesrc] = "TODO"
                    if donesrc not in routing_graph_srcs_dsts:
                        routing_graph_srcs_dsts[donesrc] = set([donedst])
                    else:
                        routing_graph_srcs_dsts[donesrc].add(donedst)
                else:
                    num_failed += 1

        if (time.time() - last_save_time >= 5) or (len(maybe_pairs_to_test) == 0):
            try:
                os.remove('work-lab-state.json.bak')
            except FileNotFoundError:
                pass
            try:
                os.remove('work-interconnect.json.bak')
            except FileNotFoundError:
                pass
            shutil.move('work-lab-state.json', 'work-lab-state.json.bak')
            shutil.move('work-interconnect.json', 'work-interconnect.json.bak')

            with open("work-lab-state.json", 'w') as f:
                json.dump(fuzzing_state, f, sort_keys=True, indent=4, separators=(',', ': '))
            with open("work-interconnect.json", 'w') as f:
                json.dump(routing_graph_dsts_srcs, f, sort_keys=True, indent=4, separators=(',', ': '))

            last_save_time = time.time()

        print("Currently, there are {} routes that worked, {} routes that failed, {} routes unknown".format(num_worked, num_failed, num_maybe))

        if len(maybe_pairs_to_test) == 0:
            break

        src, dst = random.choice(tuple(maybe_pairs_to_test))

        if (src, dst) in outstanding_tests:
            continue

        src_is_lut = src.startswith("LE_BUFFER")
        dst_is_lut = dst.startswith("LOCAL_INTERCONNECT")
        assert src_is_lut or dst_is_lut
        assert not (src_is_lut and dst_is_lut)
        # print(src, dst, src_is_lut, dst_is_lut)

        if src_is_lut:
            lutX, lutY, lutII = parse_xysi(src[10:])
            dst_to_out_path = route_to_output(routing_graph_srcs_dsts, dst)
            if dst_to_out_path is None:
                continue
            dst_to_out_path = [src] + dst_to_out_path
            # print(dst_to_out_path)

            src_A_to_in_path = None
            src_B_to_in_path = None

            for li_I_A in range(26):
                for li_I_B in range(26):
                    if li_I_A == li_I_B:
                        continue

                    maybe_A_src_to_in_path = route_to_input(routing_graph_dsts_srcs, "LOCAL_INTERCONNECT:X{}Y{}S0I{}".format(lutX, lutY, li_I_A), dst_to_out_path)
                    maybe_B_src_to_in_path = route_to_input(routing_graph_dsts_srcs, "LOCAL_INTERCONNECT:X{}Y{}S0I{}".format(lutX, lutY, li_I_B), dst_to_out_path + maybe_A_src_to_in_path)
                    if maybe_A_src_to_in_path is not None and maybe_B_src_to_in_path is not None:
                        if len(set(dst_to_out_path) & set(maybe_A_src_to_in_path)) == 0 and len(set(dst_to_out_path) & set(maybe_B_src_to_in_path)) == 0 and len(set(maybe_A_src_to_in_path) & set(maybe_B_src_to_in_path)) == 0:
                            src_A_to_in_path = maybe_A_src_to_in_path
                            src_B_to_in_path = maybe_B_src_to_in_path
                            break
            # print(src_A_to_in_path)

            if src_A_to_in_path is None:
                continue
            if src_B_to_in_path is None:
                continue
            # print(src_B_to_in_path)

            if len(set(dst_to_out_path) & set(src_A_to_in_path)) != 0:
                print("BUG!", dst_to_out_path, src_A_to_in_path)
                continue
            if len(set(dst_to_out_path) & set(src_B_to_in_path)) != 0:
                print("BUG!", dst_to_out_path, src_B_to_in_path)
                continue
            if len(set(src_B_to_in_path) & set(src_A_to_in_path)) != 0:
                print("BUG!", src_B_to_in_path, src_A_to_in_path)
                continue

            src_A_to_in_path = src_A_to_in_path[::-1]
            src_B_to_in_path = src_B_to_in_path[::-1]

            io_A_for_inp = None
            io_B_for_inp = None
            ios_A_for_inp = inp_to_io2(src_A_to_in_path[0])
            ios_B_for_inp = inp_to_io2(src_B_to_in_path[0])
            for aainp in ios_A_for_inp:
                for bbinp in ios_B_for_inp:
                    if aainp != bbinp:
                        io_A_for_inp = aainp
                        io_B_for_inp = bbinp
                        break
            if io_A_for_inp is None or io_B_for_inp is None or io_A_for_inp == io_B_for_inp:
                continue

            outp_local_int = dst_to_out_path[-1]
            assert outp_local_int.startswith("LOCAL_INTERCONNECT")
            outpX, outpY, _ = parse_xysi(outp_local_int[19:])
            io_for_outp = None
            for II in range(4):
                maybe_io_for_outp = "IOC_X{}_Y{}_N{}".format(outpX, outpY, II)
                if maybe_io_for_outp != io_A_for_inp and maybe_io_for_outp != io_B_for_inp:
                    io_for_outp = maybe_io_for_outp
                    break
            if io_for_outp is None:
                continue
            if io_for_outp == io_A_for_inp or io_for_outp == io_B_for_inp:
                continue

            # Finally ready to commit to paths
            print("Testing {} -> {} ({}; {}; {})".format(src, dst, src_A_to_in_path, src_B_to_in_path, dst_to_out_path))
            outstanding_tests.add((src, dst))
            workqueue.put((src_A_to_in_path, src_B_to_in_path, dst_to_out_path, io_A_for_inp, io_B_for_inp, io_for_outp, lutX, lutY, lutII // 2, src, dst))
            # workqueue.put((src_to_in_path + dst_to_out_path, io_for_inp, io_for_outp, src, dst))
        else:
            lutX, lutY, li_A_I = parse_xysi(dst[19:])

            src_A_to_in_path = route_to_input(routing_graph_dsts_srcs, src)
            if src_A_to_in_path is None:
                continue
            src_A_to_in_path = [dst] + src_A_to_in_path
            # print(src_A_to_in_path)

            dst_to_out_path = None
            src_B_to_in_path = None

            lutI = None
            for II in range(20):
                for li_I in range(26):
                    if li_I == li_A_I:
                        continue

                    maybe_dst_to_out_path = route_to_output(routing_graph_srcs_dsts, "LE_BUFFER:X{}Y{}S0I{}".format(lutX, lutY, II), src_A_to_in_path)
                    maybe_B_src_to_in_path = route_to_input(routing_graph_dsts_srcs, "LOCAL_INTERCONNECT:X{}Y{}S0I{}".format(lutX, lutY, li_I), maybe_dst_to_out_path + src_A_to_in_path)
                    if maybe_dst_to_out_path is not None and maybe_B_src_to_in_path is not None:
                        if len(set(maybe_dst_to_out_path) & set(src_A_to_in_path)) == 0 and len(set(maybe_dst_to_out_path) & set(maybe_B_src_to_in_path)) == 0 and len(set(src_A_to_in_path) & set(maybe_B_src_to_in_path)) == 0:
                            dst_to_out_path = maybe_dst_to_out_path
                            src_B_to_in_path = maybe_B_src_to_in_path
                            lutI = II // 2
                            break

            if dst_to_out_path is None:
                continue
            if src_B_to_in_path is None:
                continue
            # print(src_B_to_in_path)

            if len(set(dst_to_out_path) & set(src_A_to_in_path)) != 0:
                print("BUG!", dst_to_out_path, src_A_to_in_path)
                continue
            if len(set(dst_to_out_path) & set(src_B_to_in_path)) != 0:
                print("BUG!", dst_to_out_path, src_B_to_in_path)
                continue
            if len(set(src_B_to_in_path) & set(src_A_to_in_path)) != 0:
                print("BUG!", src_B_to_in_path, src_A_to_in_path)
                continue

            src_A_to_in_path = src_A_to_in_path[::-1]
            src_B_to_in_path = src_B_to_in_path[::-1]

            io_A_for_inp = None
            io_B_for_inp = None
            ios_A_for_inp = inp_to_io2(src_A_to_in_path[0])
            ios_B_for_inp = inp_to_io2(src_B_to_in_path[0])
            for aainp in ios_A_for_inp:
                for bbinp in ios_B_for_inp:
                    if aainp != bbinp:
                        io_A_for_inp = aainp
                        io_B_for_inp = bbinp
                        break
            if io_A_for_inp is None or io_B_for_inp is None or io_A_for_inp == io_B_for_inp:
                continue

            outp_local_int = dst_to_out_path[-1]
            assert outp_local_int.startswith("LOCAL_INTERCONNECT")
            outpX, outpY, _ = parse_xysi(outp_local_int[19:])
            io_for_outp = None
            for II in range(4):
                maybe_io_for_outp = "IOC_X{}_Y{}_N{}".format(outpX, outpY, II)
                if maybe_io_for_outp != io_A_for_inp and maybe_io_for_outp != io_B_for_inp:
                    io_for_outp = maybe_io_for_outp
                    break
            if io_for_outp is None:
                continue
            if io_for_outp == io_A_for_inp or io_for_outp == io_B_for_inp:
                continue

            # Finally ready to commit to paths
            print("Testing {} -> {} ({}; {}; {})".format(src, dst, src_A_to_in_path, src_B_to_in_path, dst_to_out_path))
            outstanding_tests.add((src, dst))
            workqueue.put((src_A_to_in_path, src_B_to_in_path, dst_to_out_path, io_A_for_inp, io_B_for_inp, io_for_outp, lutX, lutY, lutI, src, dst))
            # workqueue.put((src_to_in_path + dst_to_out_path, io_for_inp, io_for_outp, src, dst))

def fuzz_a_route_ioout(workdir, vmdir, path, inp, outp, my_wire_to_quartus_wire, srcname, dstname):
    with open(workdir + '/maxvtest.qsf', 'w') as f:
        f.write(QSF_TMPL.format(inp, outp))

    with open(workdir + '/maxvtest.rcf', 'w') as f:
        f.write("signal_name = a {\n")
        for pathelem in path:
            if pathelem in my_wire_to_quartus_wire:
                pathelem = my_wire_to_quartus_wire[pathelem]
            f.write("    {};\n".format(pathelem))
        f.write("    zero_or_more, *;\n")
        f.write("    dest = ( o, DATAIN );\n")
        f.write("}\n")

    while True:
        try:
            run_one_flow(vmdir, False, True, False)
            break
        except Exception:
            pass

    success = True
    with open(workdir + '/output_files/maxvtest.fit.rpt', 'r') as f:
        rptdata = f.read()
        if "Cannot route signal \"a\" to atom \"o\"" in rptdata:
            success = False
        assert "multiple usages of a single routing resource" not in rptdata

    if success:
        shutil.copy(workdir + '/output_files/maxvtest.fit.rpt', 'ioout-full-fuzz/from_{}_to_{}.fit.rpt'.format(srcname, dstname))
        shutil.copy(workdir + '/output_files/maxvtest.pof', 'ioout-full-fuzz/from_{}_to_{}.pof'.format(srcname, dstname))
        shutil.copy(workdir + '/maxvtest.rcf', 'ioout-full-fuzz/from_{}_to_{}.rcf'.format(srcname, dstname))

    return success

def threadfn_ioout(workqueue, donequeue, my_wire_to_quartus_wire, threadi):
    MYDIR = BASE_DIR + '/ioout-full-fuzz/thread{}'.format(threadi)
    VMDIR = "ioout-full-fuzz/thread{}".format(threadi)
    shutil.copytree(BASE_DIR + '/route-fuzz-seed', MYDIR)

    while True:
        try:
            x = workqueue.get()
            if x is None:
                donequeue.put(None)
                continue
            path, inp, outp, srcname, dstname = x
        except queue.Empty:
            continue

        success = fuzz_a_route_ioout(MYDIR, VMDIR, path, inp, outp, my_wire_to_quartus_wire, srcname, dstname)
        donequeue.put((srcname, dstname, success))

def do_fuzz_ioout(inp_state_fn, inp_route_fn, my_wire_to_quartus_wire):
    os.mkdir(BASE_DIR + '/ioout-full-fuzz')

    with open(inp_state_fn, 'r') as f:
        fuzzing_state = json.load(f)
    with open(inp_route_fn, 'r') as f:
        # Index first by dst, then by src
        # Lists ways to get _onto_ a wire
        routing_graph_dsts_srcs = json.load(f)

    # Invert the routing graph
    routing_graph_srcs_dsts = {}
    for dst, srcs in routing_graph_dsts_srcs.items():
        for src in srcs:
            if src not in routing_graph_srcs_dsts:
                routing_graph_srcs_dsts[src] = {dst}
            else:
                routing_graph_srcs_dsts[src].add(dst)

    with open("debug-invert-graph.json", 'w') as f:
        json.dump({k: list(v) for k, v in routing_graph_srcs_dsts.items()}, f, sort_keys=True, indent=4, separators=(',', ': '))

    with open("work-ioout-state.json", 'w') as f:
        json.dump(fuzzing_state, f, sort_keys=True, indent=4, separators=(',', ': '))
    with open("work-interconnect.json", 'w') as f:
        json.dump(routing_graph_dsts_srcs, f, sort_keys=True, indent=4, separators=(',', ': '))

    # For stats, and a cache
    num_worked = 0
    num_failed = 0
    num_maybe = 0
    maybe_pairs_to_test = set()
    for dst, srcs in fuzzing_state.items():
        for src, state in srcs.items():
            if state == True:
                num_worked += 1
            elif state == False:
                num_failed += 1
            elif state == "maybe":
                num_maybe += 1
                maybe_pairs_to_test.add((src, dst))
            else:
                raise Exception()

    workqueue = queue.Queue(2 * NTHREADS)
    donequeue = queue.Queue()

    last_save_time = time.time()
    outstanding_tests = set()

    for threadi in range(NTHREADS):
        t = threading.Thread(target=threadfn_ioout, args=(workqueue, donequeue, my_wire_to_quartus_wire, threadi))
        t.start()

    while len(maybe_pairs_to_test):
        while True:
            try:
                doneitem = donequeue.get(block=False)
            except queue.Empty:
                break

            if doneitem is not None:
                donesrc, donedst, donesuccess = doneitem
                print("{} -> {} ==> {}".format(donesrc, donedst, donesuccess))

                outstanding_tests.remove((donesrc, donedst))
                if (donesrc, donedst) in maybe_pairs_to_test:
                    maybe_pairs_to_test.remove((donesrc, donedst))
                else:
                    print("BUG", donesrc, donedst)
                num_maybe -= 1
                fuzzing_state[donedst][donesrc] = donesuccess
                if donesuccess:
                    num_worked += 1
                    if donedst not in routing_graph_dsts_srcs:
                        routing_graph_dsts_srcs[donedst] = {donesrc: "TODO"}
                    else:
                        routing_graph_dsts_srcs[donedst][donesrc] = "TODO"
                    if donesrc not in routing_graph_srcs_dsts:
                        routing_graph_srcs_dsts[donesrc] = set([donedst])
                    else:
                        routing_graph_srcs_dsts[donesrc].add(donedst)
                else:
                    num_failed += 1

        if (time.time() - last_save_time >= 5) or (len(maybe_pairs_to_test) == 0):
            try:
                os.remove('work-ioout-state.json.bak')
            except FileNotFoundError:
                pass
            try:
                os.remove('work-interconnect.json.bak')
            except FileNotFoundError:
                pass
            shutil.move('work-ioout-state.json', 'work-ioout-state.json.bak')
            shutil.move('work-interconnect.json', 'work-interconnect.json.bak')

            with open("work-ioout-state.json", 'w') as f:
                json.dump(fuzzing_state, f, sort_keys=True, indent=4, separators=(',', ': '))
            with open("work-interconnect.json", 'w') as f:
                json.dump(routing_graph_dsts_srcs, f, sort_keys=True, indent=4, separators=(',', ': '))

            last_save_time = time.time()

        print("Currently, there are {} routes that worked, {} routes that failed, {} routes unknown".format(num_worked, num_failed, num_maybe))

        if len(maybe_pairs_to_test) == 0:
            break

        src, dst = random.choice(tuple(maybe_pairs_to_test))

        if (src, dst) in outstanding_tests:
            continue

        assert src.startswith("IO_DATAIN:")

        dst_to_out_path = route_to_output(routing_graph_srcs_dsts, dst)
        if dst_to_out_path is None:
            continue

        if src in dst_to_out_path:
            continue

        io_for_inp = inp_to_io(src)

        outp_local_int = dst_to_out_path[-1]
        assert outp_local_int.startswith("LOCAL_INTERCONNECT")
        outpX, outpY, _ = parse_xysi(outp_local_int[19:])

        io_for_outp = None
        for II in range(4):
            maybe_io_for_outp = "IOC_X{}_Y{}_N{}".format(outpX, outpY, II)
            if maybe_io_for_outp != io_for_inp:
                io_for_outp = maybe_io_for_outp
                break
        if io_for_outp is None:
            continue
        if io_for_outp == io_for_inp:
            continue

        print("Testing {} -> {}".format(src, dst))
        outstanding_tests.add((src, dst))
        workqueue.put(([src] + dst_to_out_path, io_for_inp, io_for_outp, src, dst))

def main():
    with open('my_wire_to_quartus_wire.json', 'r') as f:
        my_wire_to_quartus_wire = json.load(f)
    quartus_wire_to_my_wire = {v: k for (k, v) in my_wire_to_quartus_wire.items()}

    cmd = sys.argv[1]
    if cmd=='prep':
        prep_all_routes(sys.argv[2], my_wire_to_quartus_wire)
    elif cmd=='fuzz':
        do_fuzz(sys.argv[2], sys.argv[3], my_wire_to_quartus_wire)
    elif cmd=='update':
        update_state(sys.argv[2], sys.argv[3], sys.argv[4])
    elif cmd=='prep2':
        prep_all_routes_lab(sys.argv[2], my_wire_to_quartus_wire)
    elif cmd=='fuzz2':
        do_fuzz_lab(sys.argv[2], sys.argv[3], my_wire_to_quartus_wire)
    elif cmd=='prep3':
        prep_all_routes_lab2(sys.argv[2], my_wire_to_quartus_wire)
    elif cmd=='prep4':
        prep_all_routes_lab3(sys.argv[2], my_wire_to_quartus_wire)
    elif cmd=='prep-ioout':
        prep_all_routes_ioout(sys.argv[2], my_wire_to_quartus_wire)
    elif cmd=='fuzz3':
        do_fuzz_ioout(sys.argv[2], sys.argv[3], my_wire_to_quartus_wire)
    else:
        raise Exception()

if __name__=='__main__':
    main()
