Design Doc -
- Tells what the drone MUST do
- Do not include the language specifications and similar aspects
- WHAT needs to happen, not HOW we implemented
- Design can / should include sensors (ex. CO sensor) that the prototype may not actually have working
- Three or so drones that can be used to triangulate fire location
- Do they talk to each other? Send data back to base station?
- Features we WANT in the product. Why and how could it be implemented? (not for prototype)
- Where is processing done?

Functional Prototype -
- Implements design NEEDS in some way
- Usually only has SOME of the functionality needed
- Talk about why we chose what we did as an example for future design team
- Likely prototype features: fly up, spin around, detect fire, send message to base station

Methods - 
- Drone sends message about fire detection (distance, direction, size, degree of confidence)
- Human looks over messages / feed from the drone
- Human determines if threat is valid
- If valid, move drones closer to affected area (how close?)

High Priority Decisions -
- Flight Control Software
- Image Detection Software
