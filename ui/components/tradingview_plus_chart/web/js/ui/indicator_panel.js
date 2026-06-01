// web/js/ui/indicator_panel.js
class IndicatorPanel {
    constructor() {
        this.panelElement = document.getElementById('indicatorPanel');
        this.categories = window.indicatorCategories || [];
        this.activeIndicators = new Set();
    }
    
    init() {
        console.log('🚀 初始化指标面板...');
        
        if (!this.panelElement) {
            console.error('❌ 指标面板元素未找到');
            return false;
        }
        
        this.renderPanel();
        this.bindEvents();
        
        console.log('✅ 指标面板初始化完成');
        return true;
    }
    
    renderPanel() {
        // 清空面板
        this.panelElement.innerHTML = '';
        
        // 遍历分类
        this.categories.forEach(category => {
            const categoryElement = this.createCategoryElement(category);
            this.panelElement.appendChild(categoryElement);
        });
    }
    
    createCategoryElement(category) {
        const container = document.createElement('div');
        container.className = 'indicator-category';
        
        // 创建标题
        const title = document.createElement('div');
        title.className = 'category-title';
        title.textContent = category.name;
        title.addEventListener('click', () => this.toggleCategory(container));
        
        // 创建内容容器
        const content = document.createElement('div');
        content.className = 'category-content';
        
        // 创建指标按钮
        category.indicators.forEach(indicator => {
            const button = this.createIndicatorButton(indicator);
            content.appendChild(button);
        });
        
        container.appendChild(title);
        container.appendChild(content);
        
        return container;
    }
    
    createIndicatorButton(indicator) {
        const button = document.createElement('button');
        button.className = 'indicator-button';
        button.setAttribute('data-indicator', indicator.key);
        button.textContent = `${indicator.name}`;
        button.title = `${indicator.name} (${indicator.en})`;
        
        // 设置样式
        Object.assign(button.style, {
            padding: '6px 8px',
            margin: '2px',
            border: '1px solid #2a2e39',
            background: '#131722',
            color: '#d1d4dc',
            cursor: 'pointer',
            borderRadius: '4px',
            fontSize: '11px',
            textAlign: 'center',
            transition: 'all 0.2s ease',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis'
        });
        
        return button;
    }
    
    toggleCategory(container) {
        const content = container.querySelector('.category-content');
        if (content.style.display === 'none') {
            content.style.display = 'grid';
        } else {
            content.style.display = 'none';
        }
    }
    
    bindEvents() {
        // 事件委托处理按钮点击
        this.panelElement.addEventListener('click', (event) => {
            const button = event.target.closest('.indicator-button');
            if (!button) return;
            
            const indicatorKey = button.getAttribute('data-indicator');
            this.handleIndicatorClick(indicatorKey, button);
        });
    }
    
    handleIndicatorClick(indicatorKey, button) {
        const isActive = button.classList.contains('active');
        
        if (isActive) {
            this.hideIndicator(indicatorKey, button);
        } else {
            this.showIndicator(indicatorKey, button);
        }
    }
    
    showIndicator(indicatorKey, button) {
        button.classList.add('active');
        button.style.backgroundColor = '#2962FF';
        button.style.color = 'white';
        button.style.borderColor = '#2962FF';
        
        this.activeIndicators.add(indicatorKey);
        
        // 通知Python添加指标
        if (window.pythonBridge && window.pythonBridge.notify) {
            window.pythonBridge.notify('indicator_toggle', {
                indicator: indicatorKey,
                state: true
            });
        }
    }
    
    hideIndicator(indicatorKey, button) {
        button.classList.remove('active');
        button.style.backgroundColor = '#131722';
        button.style.color = '#d1d4dc';
        button.style.borderColor = '#2a2e39';
        
        this.activeIndicators.delete(indicatorKey);
        
        // 通知Python移除指标
        if (window.pythonBridge && window.pythonBridge.notify) {
            window.pythonBridge.notify('indicator_toggle', {
                indicator: indicatorKey,
                state: false
            });
        }
    }
}

// 导出到全局
window.IndicatorPanel = new IndicatorPanel();