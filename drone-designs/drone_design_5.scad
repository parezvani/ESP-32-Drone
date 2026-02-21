/*
  ESP32-C3 drone frame (OpenSCAD model)
  - 3.5" to 4.0" prop-ready layout
  - SunnySky R1106 motors
  - ESP32-C3-DevKit-RUST-1 controller
*/

$fn = 80;

// Visual options
show_electronics_mockup = false;
show_esp32_header_pads = true;

// Main frame geometry (mm)
// v5 lightweight tuning: thinner shell while preserving electronics fit
body_length = 96;
body_width = 68;
body_height = 24;
body_corner_radius = 7;
floor_thickness = 2.5;
wall_thickness = 2.5;

// Motor layout (extended for larger prop options)
motor_center_offset = 64; // motor centers at (+/-x, +/-y)
arm_width = 10.0;
arm_thickness = 5.4;
arm_root_inset_x = 10;
arm_root_inset_y = 7;

// Motor pod geometry
motor_can_d = 14.2; // SunnySky R1106 rotor/body diameter
motor_can_l = 13.6; // SunnySky R1106 body length
motor_pod_outer_d = 19;
motor_pod_inner_d = 15.0; // +0.4 mm radial clearance per side for print tolerance
motor_pod_height = 17;
motor_mount_floor = 1.8;
motor_mount_bcd = 9; // SunnySky schematic: 4xM2 on 9 mm bolt-circle diameter
motor_mount_hole_center_r = motor_mount_bcd / 2;
motor_mount_hole_d = 2.2; // M2 clearance
motor_wire_notch_w = 6.2; // side opening for 3 motor wires
motor_wire_notch_h = 4.4;
motor_wire_notch_depth = 4.7; // deep enough to break through pod wall
enable_arm_frame_wire_notches = true;
arm_frame_wire_notch_w = 6.2;
arm_frame_wire_notch_h = 6.4;
arm_frame_wire_inboard_len = 8.0; // extend past arm root into frame pocket
arm_frame_wire_into_pod = 2.8; // start trench inside pod OD so cutout passes through pod wall

motor_pod_cavity_h = motor_pod_height - motor_mount_floor;
motor_pod_radial_clearance = (motor_pod_inner_d - motor_can_d) / 2;
motor_pod_axial_clearance = motor_pod_cavity_h - motor_can_l;

assert(motor_pod_radial_clearance >= 0.3, "Motor pod inner diameter too tight for SunnySky R1106.");
assert(motor_pod_axial_clearance >= 0.8, "Motor pod cavity height too short for SunnySky R1106.");

// ESP32-C3-DevKit-RUST-1 geometry from KiCad (mm)
// KiCad board X (22.86) is mapped to frame Y.
// KiCad board Y (63.50) is mapped to frame X.
esp32_board_kicad_x = 22.86;
esp32_board_kicad_y = 63.50;

esp32_corner_r_small = 0.508;
esp32_corner_r_top_right = 0.762;

esp32_hole_center_from_left = 2.54;
esp32_hole_center_from_bottom = 2.54;
esp32_hole_d = 3.048;

esp32_hole_spacing_x = esp32_board_kicad_y - 2 * esp32_hole_center_from_bottom; // 58.42
esp32_hole_spacing_y = esp32_board_kicad_x - 2 * esp32_hole_center_from_left; // 17.78

esp32_mount_hole_d = 3.25; // clearance around 3.048 mm board holes
esp32_standoff_d = 6;
esp32_standoff_h = 6;

// Strap slots in floor for battery hold-down
strap_slot_count = 4;
strap_slot_pitch = 16;
strap_slot_length = 5;
strap_slot_width = 24;

// Side-wall lightening windows
enable_side_lightening = true;
side_window_height = 9.0;
side_window_z_offset = 0.0; // fine-tune vertical position while keeping windows centered
long_side_window_length = 14.0;
long_side_window_x_offset = 18.0;
short_side_window_length = 8.0;
short_side_window_y_offset = 12.0;
side_window_corner_r = 2.0;

// Mock electronics (for fit visualization only)
esp32_board_length = esp32_board_kicad_y; // shown along frame X
esp32_board_width = esp32_board_kicad_x; // shown along frame Y
esp32_board_thickness = 1.6;
usb_c_overhang = 0.31; // from board edge using F.CrtYd
battery_connector_x = 2.54; // KiCad X
battery_connector_y = 31.75; // centered on board
battery_length = 70;
battery_width = 35;
battery_height = 24;

motor_to_motor_side = 2 * motor_center_offset;
motor_to_motor_diagonal = 2 * sqrt(2) * motor_center_offset;
inner_cavity_length = body_length - 2 * wall_thickness;
inner_cavity_width = body_width - 2 * wall_thickness;
inner_cavity_height = body_height - floor_thickness;
echo(str("motor_to_motor_side_mm=", motor_to_motor_side));
echo(str("motor_to_motor_diagonal_mm=", motor_to_motor_diagonal));
echo(str("inner_cavity_lwh_mm=", inner_cavity_length, "x", inner_cavity_width, "x", inner_cavity_height));
echo(str("motor_pod_radial_clearance_mm=", motor_pod_radial_clearance));
echo(str("motor_pod_axial_clearance_mm=", motor_pod_axial_clearance));
echo(str("esp32_hole_spacing_x_mm=", esp32_hole_spacing_x));
echo(str("esp32_hole_spacing_y_mm=", esp32_hole_spacing_y));

module rounded_rect_2d(l, w, r) {
    hull() {
        for (x = [-l / 2 + r, l / 2 - r], y = [-w / 2 + r, w / 2 - r]) {
            translate([x, y]) circle(r = r);
        }
    }
}

module rounded_box(l, w, h, r) {
    linear_extrude(height = h) rounded_rect_2d(l, w, r);
}

function arc_points(cx, cy, r, start_deg, end_deg, segments = 8) =
    [for (i = [0 : segments]) [cx + r * cos(start_deg + (end_deg - start_deg) * i / segments), cy + r * sin(start_deg + (end_deg - start_deg) * i / segments)]];

function esp32_outline_points() = concat(
    [[-esp32_board_length / 2 + esp32_corner_r_small, -esp32_board_width / 2]],
    [[esp32_board_length / 2 - esp32_corner_r_small, -esp32_board_width / 2]],
    arc_points(
        esp32_board_length / 2 - esp32_corner_r_small,
        -esp32_board_width / 2 + esp32_corner_r_small,
        esp32_corner_r_small,
        -90,
        0
    ),
    [[esp32_board_length / 2, esp32_board_width / 2 - esp32_corner_r_top_right]],
    arc_points(
        esp32_board_length / 2 - esp32_corner_r_top_right,
        esp32_board_width / 2 - esp32_corner_r_top_right,
        esp32_corner_r_top_right,
        0,
        90
    ),
    [[-esp32_board_length / 2 + esp32_corner_r_small, esp32_board_width / 2]],
    arc_points(
        -esp32_board_length / 2 + esp32_corner_r_small,
        esp32_board_width / 2 - esp32_corner_r_small,
        esp32_corner_r_small,
        90,
        180
    ),
    [[-esp32_board_length / 2, -esp32_board_width / 2 + esp32_corner_r_small]],
    arc_points(
        -esp32_board_length / 2 + esp32_corner_r_small,
        -esp32_board_width / 2 + esp32_corner_r_small,
        esp32_corner_r_small,
        180,
        270
    )
);

module esp32_board_2d() {
    polygon(points = esp32_outline_points());
}

module frame_arm(sx, sy) {
    root_x = sx * (body_length / 2 - arm_root_inset_x);
    root_y = sy * (body_width / 2 - arm_root_inset_y);
    motor_x = sx * motor_center_offset;
    motor_y = sy * motor_center_offset;

    hull() {
        translate([root_x, root_y, 0]) cylinder(h = arm_thickness, d = arm_width);
        translate([motor_x, motor_y, 0]) cylinder(h = arm_thickness, d = arm_width);
    }
}

module motor_pod(sx, sy) {
    motor_x = sx * motor_center_offset;
    motor_y = sy * motor_center_offset;
    translate([motor_x, motor_y, 0]) cylinder(h = motor_pod_height, d = motor_pod_outer_d);
}

module motor_wire_notch(mx, my, wire_angle) {
    // Keep notch above arm blend so the opening isn't blocked by the arm body.
    notch_z = max(
        motor_mount_floor + motor_wire_notch_h / 2 + 0.2,
        arm_thickness + motor_wire_notch_h / 2 + 0.3
    );
    notch_center_r = motor_pod_outer_d / 2 - motor_wire_notch_depth / 2 + 0.2;

    translate([mx, my, notch_z]) {
        rotate([0, 0, wire_angle]) {
            translate([notch_center_r, 0, 0]) {
                cube([motor_wire_notch_depth, motor_wire_notch_w, motor_wire_notch_h], center = true);
            }
        }
    }
}

module arm_to_frame_wire_notch(sx, sy) {
    root_x = sx * (body_length / 2 - arm_root_inset_x);
    root_y = sy * (body_width / 2 - arm_root_inset_y);
    motor_x = sx * motor_center_offset;
    motor_y = sy * motor_center_offset;

    dir_x = root_x - motor_x;
    dir_y = root_y - motor_y;
    dir_len = sqrt(dir_x * dir_x + dir_y * dir_y);
    ux = dir_x / dir_len;
    uy = dir_y / dir_len;

    // Keep this trench high enough to be open at the arm top and into the frame pocket.
    notch_z = max(
        arm_thickness - arm_frame_wire_notch_h / 2 + 0.1,
        floor_thickness + arm_frame_wire_notch_h / 2 + 0.2
    );

    start_r = max(0, motor_pod_outer_d / 2 - arm_frame_wire_into_pod);
    start_x = motor_x + ux * start_r;
    start_y = motor_y + uy * start_r;
    frame_x = root_x + ux * arm_frame_wire_inboard_len;
    frame_y = root_y + uy * arm_frame_wire_inboard_len;
    notch_len = sqrt((frame_x - start_x) * (frame_x - start_x) + (frame_y - start_y) * (frame_y - start_y));
    notch_angle = atan2(frame_y - start_y, frame_x - start_x);

    translate([(start_x + frame_x) / 2, (start_y + frame_y) / 2, notch_z]) {
        rotate([0, 0, notch_angle]) {
            cube([notch_len, arm_frame_wire_notch_w, arm_frame_wire_notch_h], center = true);
        }
    }
}

module side_lightening_cutouts() {
    side_window_z = floor_thickness + (body_height - floor_thickness) / 2 + side_window_z_offset;
    side_cut_depth = wall_thickness + 1.0;

    // Two windows per long side wall
    for (sy = [-1, 1], x = [-long_side_window_x_offset, long_side_window_x_offset]) {
        translate([x, sy * (body_width / 2 - wall_thickness / 2), side_window_z]) {
            rotate([90, 0, 0]) linear_extrude(height = side_cut_depth, center = true) {
                rounded_rect_2d(long_side_window_length, side_window_height, side_window_corner_r);
            }
        }
    }

    // Two windows per short side wall
    for (sx = [-1, 1], y = [-short_side_window_y_offset, short_side_window_y_offset]) {
        translate([sx * (body_length / 2 - wall_thickness / 2), y, side_window_z]) {
            rotate([0, 90, 0]) linear_extrude(height = side_cut_depth, center = true) {
                rounded_rect_2d(short_side_window_length, side_window_height, side_window_corner_r);
            }
        }
    }
}

module esp32_standoffs() {
    for (sx = [-1, 1], sy = [-1, 1]) {
        x = sx * esp32_hole_spacing_x / 2;
        y = sy * esp32_hole_spacing_y / 2;
        translate([x, y, floor_thickness]) cylinder(h = esp32_standoff_h, d = esp32_standoff_d);
    }
}

module frame_cutouts() {
    // Electronics pocket
    translate([0, 0, floor_thickness]) {
        rounded_box(
            body_length - 2 * wall_thickness,
            body_width - 2 * wall_thickness,
            body_height - floor_thickness + 0.2,
            max(body_corner_radius - wall_thickness, 2)
        );
    }

    // Motor cavities + mount holes + wire notch
    for (sx = [-1, 1], sy = [-1, 1]) {
        mx = sx * motor_center_offset;
        my = sy * motor_center_offset;
        root_x = sx * (body_length / 2 - arm_root_inset_x);
        root_y = sy * (body_width / 2 - arm_root_inset_y);
        wire_angle = atan2(root_y - my, root_x - mx);
        // Keep notch centered between two holes per motor drawing 45 deg note.

        translate([mx, my, motor_mount_floor]) {
            cylinder(h = motor_pod_height - motor_mount_floor + 0.2, d = motor_pod_inner_d);
        }

        for (i = [0 : 3]) {
            hole_angle = wire_angle + 45 + i * 90;
            hole_x = motor_mount_hole_center_r * cos(hole_angle);
            hole_y = motor_mount_hole_center_r * sin(hole_angle);
            translate([mx + hole_x, my + hole_y, -0.1]) {
                cylinder(h = motor_mount_floor + 0.4, d = motor_mount_hole_d);
            }
        }

        motor_wire_notch(mx, my, wire_angle);

        if (enable_arm_frame_wire_notches) {
            arm_to_frame_wire_notch(sx, sy);
        }
    }

    // Battery strap slots
    for (i = [0 : strap_slot_count - 1]) {
        x = (i - (strap_slot_count - 1) / 2) * strap_slot_pitch;
        translate([x, 0, floor_thickness / 2]) {
            cube([strap_slot_length, strap_slot_width, floor_thickness + 0.4], center = true);
        }
    }

    if (enable_side_lightening) {
        side_lightening_cutouts();
    }

}

module drone_frame() {
    difference() {
        union() {
            rounded_box(body_length, body_width, body_height, body_corner_radius);

            for (sx = [-1, 1], sy = [-1, 1]) {
                frame_arm(sx, sy);
                motor_pod(sx, sy);
            }

            esp32_standoffs();

        }
        frame_cutouts();
    }
}

module electronics_mockup() {
    board_center_z = floor_thickness + esp32_standoff_h + esp32_board_thickness / 2;

    color([0.10, 0.10, 0.10, 0.95]) {
        translate([0, 0, board_center_z]) linear_extrude(height = esp32_board_thickness, center = true) {
            difference() {
                esp32_board_2d();
                for (sx = [-1, 1], sy = [-1, 1]) {
                    x = sx * esp32_hole_spacing_x / 2;
                    y = sy * esp32_hole_spacing_y / 2;
                    translate([x, y]) circle(d = esp32_hole_d);
                }
            }
        }
    }

    color([0.78, 0.78, 0.78, 0.95]) {
        // USB-C body at +X board edge with courtyard overhang
        translate([esp32_board_length / 2 + usb_c_overhang / 2, 0, board_center_z + 3]) {
            cube([usb_c_overhang + 7.8, 9.0, 6.0], center = true);
        }

        // Main RF can / component envelope
        translate([8, 0, board_center_z + 2.4]) cube([18, 16, 4.8], center = true);

        // Approximate battery JST area from board coordinates
        connector_x = battery_connector_y - esp32_board_length / 2;
        connector_y = battery_connector_x - esp32_board_width / 2;
        translate([connector_x, connector_y, board_center_z + 2]) cube([9, 6, 3.8], center = true);
    }

    if (show_esp32_header_pads) {
        // Left row: X=1.27 from left, 16 pins from Y=11.43..49.53
        color([0.85, 0.68, 0.16, 0.95]) {
            for (i = [0 : 15]) {
                pin_kicad_x = 1.27;
                pin_kicad_y = 11.43 + i * 2.54;
                pin_x = pin_kicad_y - esp32_board_length / 2;
                pin_y = pin_kicad_x - esp32_board_width / 2;
                translate([pin_x, pin_y, board_center_z + 0.9]) cylinder(h = 1.2, d = 1.1);
            }

            // Right row: X=21.59 from left, 12 pins from Y=21.59..49.53
            for (i = [0 : 11]) {
                pin_kicad_x = 21.59;
                pin_kicad_y = 21.59 + i * 2.54;
                pin_x = pin_kicad_y - esp32_board_length / 2;
                pin_y = pin_kicad_x - esp32_board_width / 2;
                translate([pin_x, pin_y, board_center_z + 0.9]) cylinder(h = 1.2, d = 1.1);
            }
        }
    }

    color([0.16, 0.16, 0.19, 0.88]) {
        translate([0, 0, body_height + battery_height / 2 + 1]) cube([battery_length, battery_width, battery_height], center = true);
    }
}

color([0.78, 0.80, 0.83, 1.0]) drone_frame();
if (show_electronics_mockup) electronics_mockup();
