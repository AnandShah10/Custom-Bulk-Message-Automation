document.addEventListener('DOMContentLoaded', () => {
    const chatContainer = document.getElementById('support-bot-container');
    const chatWindow = document.getElementById('chat-window');
    const toggleChat = document.getElementById('toggle-chat');
    const closeChat = document.getElementById('close-chat');
    const iconClosed = document.getElementById('icon-closed');
    const iconOpen = document.getElementById('icon-open');
    const chatMessages = document.getElementById('chat-messages');
    const chatInput = document.getElementById('chat-input');
    const sendChat = document.getElementById('send-chat');

    let isOpen = false;
    let isTyping = false;

    // Toggle Chat Visibility
    function setChatState(state) {
        isOpen = state;
        if (isOpen) {
            chatWindow.classList.remove('opacity-0', 'scale-90', 'translate-y-10', 'invisible');
            iconClosed.classList.add('opacity-0');
            iconOpen.classList.remove('opacity-0');
            chatInput.focus();
        } else {
            chatWindow.classList.add('opacity-0', 'scale-90', 'translate-y-10', 'invisible');
            iconClosed.classList.remove('opacity-0');
            iconOpen.classList.add('opacity-0');
        }
    }

    toggleChat.addEventListener('click', () => setChatState(!isOpen));
    closeChat.addEventListener('click', () => setChatState(false));

    // Message Rendering Helpers
    function appendMessage(role, content) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `flex ${role === 'user' ? 'justify-end' : 'items-start'} gap-3 animate-in slide-in-from-bottom-2 duration-300`;
        
        if (role === 'user') {
            msgDiv.innerHTML = `<div class="bg-blue-600 p-3.5 rounded-2xl rounded-tr-none max-w-[85%] text-sm text-white shadow-lg shadow-blue-500/20">${content}</div>`;
            chatMessages.appendChild(msgDiv);
        } else {
            // Bot message with avatar and empty content container for typing
            msgDiv.innerHTML = `
                <div class="w-8 h-8 rounded-lg bg-white/5 flex items-center justify-center shrink-0 mt-1"><span class="text-xs">🤖</span></div>
                <div class="bg-white/5 border border-white/10 p-3.5 rounded-2xl rounded-tl-none max-w-[85%] text-sm text-gray-200 leading-relaxed bot-content"></div>`;
            chatMessages.appendChild(msgDiv);
            
            const contentDiv = msgDiv.querySelector('.bot-content');
            typeEffect(contentDiv, content);
        }
        
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function typeEffect(element, html) {
        // We set the innerHTML initially but hidden, then reveal it
        // To make it look like typing while preserving HTML structure:
        element.innerHTML = html;
        const textNodes = [];
        
        function getTextNodes(node) {
            if (node.nodeType === 3) textNodes.push(node);
            else {
                for (let child of node.childNodes) getTextNodes(child);
            }
        }
        
        getTextNodes(element);
        
        // Hide all text nodes initially
        const originalTexts = textNodes.map(node => {
            const val = node.nodeValue;
            node.nodeValue = '';
            return val;
        });
        
        let nodeIdx = 0;
        let charIdx = 0;
        const speed = 15; // ms per character

        function type() {
            if (nodeIdx < textNodes.length) {
                const fullText = originalTexts[nodeIdx];
                textNodes[nodeIdx].nodeValue = fullText.substring(0, charIdx + 1);
                charIdx++;
                
                if (charIdx >= fullText.length) {
                    nodeIdx++;
                    charIdx = 0;
                }
                
                chatMessages.scrollTop = chatMessages.scrollHeight;
                setTimeout(type, speed);
            }
        }
        
        type();
    }

    function showTyping() {
        if (isTyping) return;
        isTyping = true;
        const typingDiv = document.createElement('div');
        typingDiv.id = 'typing-indicator';
        typingDiv.className = 'flex items-start gap-3 animate-pulse';
        typingDiv.innerHTML = `
            <div class="w-8 h-8 rounded-lg bg-white/5 flex items-center justify-center shrink-0 mt-1"><span class="text-xs">🤖</span></div>
            <div class="bg-white/5 border border-white/10 p-3 rounded-2xl rounded-tl-none"><div class="flex gap-1"><div class="w-1.5 h-1.5 bg-gray-500 rounded-full"></div><div class="w-1.5 h-1.5 bg-gray-500 rounded-full animate-bounce"></div><div class="w-1.5 h-1.5 bg-gray-500 rounded-full"></div></div></div>`;
        chatMessages.appendChild(typingDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function hideTyping() {
        isTyping = false;
        const typingDiv = document.getElementById('typing-indicator');
        if (typingDiv) typingDiv.remove();
    }

    // Chat Logic
    async function sendMessage() {
        const message = chatInput.value.trim();
        if (!message || isTyping) return;

        chatInput.value = '';
        appendMessage('user', message);
        showTyping();

        try {
            const response = await fetch('/support/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message })
            });

            const data = await response.json();
            hideTyping();
            appendMessage('bot', data.reply);
        } catch (error) {
            console.error('Chat error:', error);
            hideTyping();
            appendMessage('bot', "Sorry, I'm having trouble connecting right now.");
        }
    }

    sendChat.addEventListener('click', sendMessage);
    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMessage();
    });
});
