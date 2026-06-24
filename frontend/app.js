document.addEventListener('DOMContentLoaded', () => {
    initStarfield();
    makeLogoTransparent();
    const chatForm = document.getElementById('chat-form');
    const userInput = document.getElementById('user-input');
    const chatMessages = document.getElementById('chat-messages');
    const landingState = document.getElementById('landing-state');
    const chatFooter = document.getElementById('chat-footer');

    let isConversationStarted = false;

    // Helper to append message bubble to UI
    function appendMessage(role, text) {
        // Transition landing state to active chat state if this is the first message
        if (!isConversationStarted) {
            landingState.style.display = 'none';
            chatMessages.style.display = 'flex';
            chatFooter.style.display = 'flex';
            
            // Relocate the chat-form from the landing state to the bottom footer
            chatFooter.appendChild(chatForm);
            
            isConversationStarted = true;
        }

        const messageDiv = document.createElement('div');
        messageDiv.classList.add('message', role);

        const nameDiv = document.createElement('div');
        nameDiv.classList.add('sender-name');
        nameDiv.textContent = role === 'user' ? 'You' : 'Dhyan AI';

        const textDiv = document.createElement('div');
        textDiv.classList.add('message-text');
        textDiv.textContent = text;

        messageDiv.appendChild(nameDiv);
        messageDiv.appendChild(textDiv);
        chatMessages.appendChild(messageDiv);
        
        // Auto scroll to bottom
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    // =========================================================================
    // BACKEND INTEGRATION PLACEHOLDER (LLM CONNECTION)
    // =========================================================================
    /**
     * Use this function to connect the frontend to your LLM API.
     * Replace the mock response logic below with your fetch/axios request.
     * 
     * Example integration with your Python model:
     * 
     * async function getAIMessageResponse(userMessage) {
     *     try {
     *         const response = await fetch('http://localhost:8000/api/chat', {
     *             method: 'POST',
     *             headers: { 'Content-Type': 'application/json' },
     *             body: JSON.stringify({ 
     *                 email: 'customer@gmail.com',
     *                 message: userMessage 
     *             })
     *         });
     *         const data = await response.json();
     *         return data.reply; // Extract the reply returned by your LLM
     *     } catch (error) {
     *         console.error("API connection failed:", error);
     *         return "Sorry, I had trouble connecting to Dhyan AI. Please make sure the server is running.";
     *     }
     * }
     */
    async function getAIMessageResponse(userMessage) {
        // Simulated API latency (1.0 second delay)
        await new Promise(resolve => setTimeout(resolve, 1000));
        
        const lowerMsg = userMessage.toLowerCase();
        
        // Mock keyword responses to demonstrate working flow
        if (lowerMsg.includes('customize') || lowerMsg.includes('size')) {
            return "For size customization of a Track Suit, Dhyani Tracks requires: Chest, Shoulder, Sleeve Length, T-Shirt Length, Waist, Hip, Thigh, Ankle, and Lower Length. Size customization charges are 200 INR on top of the base product price.";
        }
        if (lowerMsg.includes('price') || lowerMsg.includes('how much') || lowerMsg.includes('cost')) {
            return "The base price of our premium Track Suit (DT-003) is 1900 INR. If you customize, size customization is 200 INR (Total: 2100 INR). Let me know if you would like to proceed with the purchase!";
        }
        if (lowerMsg.includes('buy') || lowerMsg.includes('purchase') || lowerMsg.includes('confirm')) {
            return "[MAIL TOOL] Success! Order confirmation email has been triggered for customer@gmail.com. An order summary has been saved to order_summary.json (Total: 2100 INR). Order status: Secured.";
        }
        
        // Dynamic simulated responses
        const mockResponses = [
            `I received your message: "${userMessage}". Dhyan AI is currently in mock-up mode for this frontend test. Try asking about "prices", "size customization", or typing "buy" to see example backend tool flows!`,
            `"${userMessage}" sounds great! As your Dhyan AI assistant, once the LLM backend is integrated, I will be able to answer your questions about sportswear orders directly. Currently, I'm displaying this simulated message to showcase our chat panel styling.`,
            `Thanks for typing: "${userMessage}". The chat panel layout is fully set up. Once the real LLM backend is hooked up, your message will be processed to return detailed insights and options.`
        ];
        
        // Select response based on the length of input
        const index = Math.abs(userMessage.length) % mockResponses.length;
        return mockResponses[index];
    }

    // Handle form submission
    chatForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const text = userInput.value.trim();
        if (!text) return;

        // 1. Append User Bubble immediately
        appendMessage('user', text);
        userInput.value = '';

        // 2. Fetch & Append AI Response (simulated)
        const responseText = await getAIMessageResponse(text);
        appendMessage('assistant', responseText);
    });

    // Starfield Animation
    function initStarfield() {
        const canvas = document.getElementById('starfield');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        
        let width = canvas.width = window.innerWidth;
        let height = canvas.height = window.innerHeight;
        
        window.addEventListener('resize', () => {
            width = canvas.width = window.innerWidth;
            height = canvas.height = window.innerHeight;
        });
        
        const numStars = 100;
        const stars = [];
        
        for (let i = 0; i < numStars; i++) {
            stars.push({
                x: Math.random() * width,
                y: Math.random() * height,
                size: Math.random() * 1.5 + 0.5,
                speed: Math.random() * 0.5 + 0.1
            });
        }
        
        function animate() {
            ctx.fillStyle = '#000000';
            ctx.fillRect(0, 0, width, height);
            
            ctx.fillStyle = '#ffffff';
            for (let i = 0; i < numStars; i++) {
                const star = stars[i];
                ctx.beginPath();
                ctx.arc(star.x, star.y, star.size, 0, Math.PI * 2);
                ctx.fill();
                
                // Move stars from right to left
                star.x -= star.speed;
                
                // Reset star if it goes offscreen
                if (star.x < 0) {
                    star.x = width;
                    star.y = Math.random() * height;
                }
            }
            
            requestAnimationFrame(animate);
        }
        
        animate();
    }

    // Dynamic Client-side transparency processor for logo
    function makeLogoTransparent() {
        const logoImg = document.querySelector('.landing-logo');
        if (!logoImg) return;
        
        logoImg.addEventListener('load', () => {
            const canvas = document.createElement('canvas');
            canvas.width = logoImg.naturalWidth;
            canvas.height = logoImg.naturalHeight;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(logoImg, 0, 0);
            
            try {
                const imgData = ctx.getImageData(0, 0, canvas.width, canvas.height);
                const data = imgData.data;
                
                // Replace any dark pixels (RGB < 40) with transparent ones
                for (let i = 0; i < data.length; i += 4) {
                    const r = data[i];
                    const g = data[i+1];
                    const b = data[i+2];
                    
                    if (r < 40 && g < 40 && b < 40) {
                        data[i+3] = 0; // Alpha 0
                    }
                }
                
                ctx.putImageData(imgData, 0, 0);
                logoImg.src = canvas.toDataURL();
            } catch (e) {
                console.warn("Could not process logo background: ", e);
            }
        }, { once: true });
        
        // Trigger load event if already completed loading
        if (logoImg.complete) {
            logoImg.dispatchEvent(new Event('load'));
        }
    }
});
