/*
  ESP32-C3 drone frame (OpenSCAD model)
  - 3.5" to 4.0" prop-ready layout
  - RCINPOWER GTS 1204 5000KV motors
  - ESP32-C3-DevKit-RUST-1 controller
*/

$fn = 80;

// Visual options
show_electronics_mockup = false;
show_esp32_header_pads = true;

// Main frame geometry (mm)
// v5 lightweight tuning: thinner shell while preserving electronics fit
body_length = 100;
body_width = 72;
body_height = 24;
body_corner_radius = 7;
floor_thickness = 2.5;
wall_thickness = 2.5;

// Motor layout (extended for larger prop options)
motor_center_offset = 74; // motor centers at (+/-x, +/-y)
arm_width = 10.0;
arm_thickness = 5.4;
arm_root_inset_x = 10;
arm_root_inset_y = 7;

// Motor pod geometry
motor_can_d = 16.1; // RCINPOWER GTS 1204 rotor/body diameter
motor_can_l = 10.9; // RCINPOWER GTS 1204 body length above the mount face
motor_pod_outer_d = 22.0;
motor_pod_inner_d = 18.0; // +0.45 mm radial clearance per side for print tolerance
motor_pod_height = 9.0;
motor_mount_floor = 1.8;
motor_mount_bcd = 9; // fit check on the real motor confirms the 4xM2 pattern sits on a 9 mm bolt circle
motor_mount_hole_center_r = motor_mount_bcd / 2;
motor_mount_hole_d = 2.2; // M2 clearance
motor_mount_center_relief_d = 5.2; // clears the center boss / wire exit feature on the motor base
motor_pod_min_wall_height = 2.0; // open-top pod only needs enough wall to register and protect the can
motor_wire_notch_w = 6.2; // side opening for 3 motor wires
motor_wire_notch_h = 4.4;
motor_wire_notch_depth = 4.7; // deep enough to break through pod wall
enable_arm_frame_wire_notches = true;
arm_frame_wire_notch_w = 6.2;
arm_frame_wire_notch_h = 21.5;
arm_frame_wire_inboard_len = 8.0; // extend past arm root into frame pocket
arm_frame_wire_into_pod = 3.2; // start trench inside pod OD so cutout passes through pod wall

motor_pod_cavity_h = motor_pod_height - motor_mount_floor;
motor_pod_radial_clearance = (motor_pod_inner_d - motor_can_d) / 2;
motor_pod_axial_clearance = motor_pod_cavity_h - motor_can_l;
motor_pod_wall_capture_h = min(motor_pod_cavity_h, motor_can_l);
motor_pod_can_exposed_h = max(0, -motor_pod_axial_clearance);

assert(motor_pod_radial_clearance >= 0.3, "Motor pod inner diameter too tight for RCINPOWER GTS 1204.");
assert(motor_pod_cavity_h >= motor_pod_min_wall_height, "Motor pod wall height is too short to retain the RCINPOWER GTS 1204.");

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
side_window_height = 12.0;
side_window_z_offset = 0.0; // fine-tune vertical position while keeping windows centered
long_side_window_length = 16.0;
long_side_window_x_offset = 18.0;
short_side_window_length = 10.0;
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
body_half_length = body_length / 2;
body_half_width = body_width / 2;
inner_cavity_length = body_length - 2 * wall_thickness;
inner_cavity_width = body_width - 2 * wall_thickness;
inner_cavity_height = body_height - floor_thickness;
inner_cavity_corner_r = max(body_corner_radius - wall_thickness, 2);
motor_cavity_cut_h = motor_pod_height - motor_mount_floor + 0.2;
motor_mount_cut_h = motor_mount_floor + 0.4;
strap_slot_cut_h = floor_thickness + 0.4;
side_cut_depth = wall_thickness + 1.0;
echo(str("motor_to_motor_side_mm=", motor_to_motor_side));
echo(str("motor_to_motor_diagonal_mm=", motor_to_motor_diagonal));
echo(str("inner_cavity_lwh_mm=", inner_cavity_length, "x", inner_cavity_width, "x", inner_cavity_height));
echo(str("motor_pod_radial_clearance_mm=", motor_pod_radial_clearance));
echo(str("motor_pod_axial_clearance_mm=", motor_pod_axial_clearance));
echo(str("motor_pod_wall_capture_mm=", motor_pod_wall_capture_h));
echo(str("motor_pod_can_exposed_mm=", motor_pod_can_exposed_h));
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

function arm_root_xy(sx, sy) = [
    sx * (body_half_length - arm_root_inset_x),
    sy * (body_half_width - arm_root_inset_y)
];

function motor_xy(sx, sy) = [sx * motor_center_offset, sy * motor_center_offset];

function esp32_hole_xy(sx, sy) = [sx * esp32_hole_spacing_x / 2, sy * esp32_hole_spacing_y / 2];

function board_xy_from_kicad(kicad_x, kicad_y) = [
    kicad_y - esp32_board_length / 2,
    kicad_x - esp32_board_width / 2
];

function xy_from_polar(r, angle_deg) = [r * cos(angle_deg), r * sin(angle_deg)];

function xy_add(a, b) = [a[0] + b[0], a[1] + b[1]];

function xy_sub(a, b) = [a[0] - b[0], a[1] - b[1]];

function xy_scale(v, scale) = [v[0] * scale, v[1] * scale];

function xy_length(v) = sqrt(v[0] * v[0] + v[1] * v[1]);

function xy_unit(from_xy, to_xy) =
    let(delta = xy_sub(to_xy, from_xy), len = xy_length(delta))
    [delta[0] / len, delta[1] / len];

function xy_midpoint(a, b) = xy_scale(xy_add(a, b), 0.5);

function xy_angle(from_xy, to_xy) = atan2(to_xy[1] - from_xy[1], to_xy[0] - from_xy[0]);

function strap_slot_x(i) = (i - (strap_slot_count - 1) / 2) * strap_slot_pitch;

module translate_xy(xy, z = 0) {
    translate([xy[0], xy[1], z]) children();
}

module motor_mount_pattern(motor_xy_pos, wire_angle) {
    translate_xy(motor_xy_pos, motor_mount_floor) {
        cylinder(h = motor_cavity_cut_h, d = motor_pod_inner_d);
    }

    translate_xy(motor_xy_pos, -0.1) {
        cylinder(h = motor_mount_cut_h, d = motor_mount_center_relief_d);
    }

    for (i = [0 : 3]) {
        hole_xy = xy_add(
            motor_xy_pos,
            xy_from_polar(motor_mount_hole_center_r, wire_angle + 45 + i * 90)
        );
        translate_xy(hole_xy, -0.1) {
            cylinder(h = motor_mount_cut_h, d = motor_mount_hole_d);
        }
    }
}

module esp32_pin_row(board_center_z, pin_kicad_x, pin_kicad_y_start, pin_count) {
    for (i = [0 : pin_count - 1]) {
        pin_xy = board_xy_from_kicad(pin_kicad_x, pin_kicad_y_start + i * 2.54);
        translate_xy(pin_xy, board_center_z + 0.9) cylinder(h = 1.2, d = 1.1);
    }
}

module frame_arm(sx, sy) {
    root_xy_pos = arm_root_xy(sx, sy);
    motor_xy_pos = motor_xy(sx, sy);

    hull() {
        translate_xy(root_xy_pos) cylinder(h = arm_thickness, d = arm_width);
        translate_xy(motor_xy_pos) cylinder(h = arm_thickness, d = arm_width);
    }
}

module motor_pod(sx, sy) {
    translate_xy(motor_xy(sx, sy)) cylinder(h = motor_pod_height, d = motor_pod_outer_d);
}

module motor_wire_notch(motor_xy_pos, wire_angle) {
    // Keep notch above arm blend so the opening isn't blocked by the arm body.
    notch_z = max(
        motor_mount_floor + motor_wire_notch_h / 2 + 0.2,
        arm_thickness + motor_wire_notch_h / 2 + 0.3
    );
    notch_center_r = motor_pod_outer_d / 2 - motor_wire_notch_depth / 2 + 0.2;

    translate_xy(motor_xy_pos, notch_z) {
        rotate([0, 0, wire_angle]) {
            translate([notch_center_r, 0, 0]) {
                cube([motor_wire_notch_depth, motor_wire_notch_w, motor_wire_notch_h], center = true);
            }
        }
    }
}

module arm_to_frame_wire_notch(sx, sy) {
    root_xy_pos = arm_root_xy(sx, sy);
    motor_xy_pos = motor_xy(sx, sy);
    unit_xy = xy_unit(motor_xy_pos, root_xy_pos);

    // Keep this trench high enough to be open at the arm top and into the frame pocket.
    notch_z = max(
        arm_thickness - arm_frame_wire_notch_h / 2 + 0.1,
        floor_thickness + arm_frame_wire_notch_h / 2 + 0.2
    );

    start_r = max(0, motor_pod_outer_d / 2 - arm_frame_wire_into_pod);
    start_xy = xy_add(motor_xy_pos, xy_scale(unit_xy, start_r));
    frame_xy = xy_add(root_xy_pos, xy_scale(unit_xy, arm_frame_wire_inboard_len));
    notch_len = xy_length(xy_sub(frame_xy, start_xy));
    notch_angle = xy_angle(start_xy, frame_xy);

    translate_xy(xy_midpoint(start_xy, frame_xy), notch_z) {
        rotate([0, 0, notch_angle]) {
            cube([notch_len, arm_frame_wire_notch_w, arm_frame_wire_notch_h], center = true);
        }
    }
}

module side_lightening_cutouts() {
    side_window_z = floor_thickness + (body_height - floor_thickness) / 2 + side_window_z_offset;

    // Two windows per long side wall
    for (sy = [-1, 1], x = [-long_side_window_x_offset, long_side_window_x_offset]) {
        translate([x, sy * (body_half_width - wall_thickness / 2), side_window_z]) {
            rotate([90, 0, 0]) linear_extrude(height = side_cut_depth, center = true) {
                rounded_rect_2d(long_side_window_length, side_window_height, side_window_corner_r);
            }
        }
    }

    // Two windows per short side wall
    for (sx = [-1, 1], y = [-short_side_window_y_offset, short_side_window_y_offset]) {
        translate([sx * (body_half_length - wall_thickness / 2), y, side_window_z]) {
            rotate([0, 90, 0]) linear_extrude(height = side_cut_depth, center = true) {
                rounded_rect_2d(short_side_window_length, side_window_height, side_window_corner_r);
            }
        }
    }
}

module esp32_standoffs() {
    for (sx = [-1, 1], sy = [-1, 1]) {
        hole_xy = esp32_hole_xy(sx, sy);
        translate_xy(hole_xy, floor_thickness) cylinder(h = esp32_standoff_h, d = esp32_standoff_d);
    }
}

module frame_cutouts() {
    // Electronics pocket
    translate([0, 0, floor_thickness]) {
        rounded_box(
            inner_cavity_length,
            inner_cavity_width,
            inner_cavity_height + 0.2,
            inner_cavity_corner_r
        );
    }

    // Motor cavities + mount holes + wire notch
    for (sx = [-1, 1], sy = [-1, 1]) {
        motor_xy_pos = motor_xy(sx, sy);
        root_xy_pos = arm_root_xy(sx, sy);
        wire_angle = xy_angle(motor_xy_pos, root_xy_pos);
        // Keep notch centered between two holes per motor drawing 45 deg note.

        motor_mount_pattern(motor_xy_pos, wire_angle);

        motor_wire_notch(motor_xy_pos, wire_angle);

        if (enable_arm_frame_wire_notches) {
            arm_to_frame_wire_notch(sx, sy);
        }
    }

    // Battery strap slots
    for (i = [0 : strap_slot_count - 1]) {
        translate([strap_slot_x(i), 0, floor_thickness / 2]) {
            cube([strap_slot_length, strap_slot_width, strap_slot_cut_h], center = true);
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
                    hole_xy = esp32_hole_xy(sx, sy);
                    translate(hole_xy) circle(d = esp32_hole_d);
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
        connector_xy = board_xy_from_kicad(battery_connector_x, battery_connector_y);
        translate_xy(connector_xy, board_center_z + 2) cube([9, 6, 3.8], center = true);
    }

    if (show_esp32_header_pads) {
        color([0.85, 0.68, 0.16, 0.95]) {
            // Left row: X=1.27 from left, 16 pins from Y=11.43..49.53
            esp32_pin_row(board_center_z, 1.27, 11.43, 16);

            // Right row: X=21.59 from left, 12 pins from Y=21.59..49.53
            esp32_pin_row(board_center_z, 21.59, 21.59, 12);
        }
    }

    color([0.16, 0.16, 0.19, 0.88]) {
        translate([0, 0, body_height + battery_height / 2 + 1]) cube([battery_length, battery_width, battery_height], center = true);
    }
}

color([0.78, 0.80, 0.83, 1.0]) drone_frame();
if (show_electronics_mockup) electronics_mockup();
