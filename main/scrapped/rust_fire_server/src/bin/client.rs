use std::io::{Read, Write};
use std::net::TcpStream;

fn main() -> std::io::Result<()> {
    // Connect to the server
    let mut stream = TcpStream::connect("127.0.0.1:7878")?;
    println!("Connected to server");

    // Build the request lines
    let req_line = "FIRE /telemetry DRONE/1.0\n";
    let telemetry_line = "Fire-Detected: yes; Fire-Distance: 120; Fire-Range: 45; Temperature: 63.4; Humidity: 21.5; Drone-ID: DRONE-01\n";

    let message = format!("{req_line}{telemetry_line}");

    // Send to server
    stream.write_all(message.as_bytes())?;
    stream.flush()?;

    // Read response
    let mut buf = [0u8; 128];
    let n = stream.read(&mut buf)?;
    let resp = String::from_utf8_lossy(&buf[..n]);
    println!("Server response: {}", resp.trim_end());

    Ok(())
}
