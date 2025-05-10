import * as DigitalBaconUI from 'DigitalBacon-UI';
import * as THREE from 'three';

export class TelescopeGUI {

    static async init(container, renderer, scene, camera, userRig) {
        await DigitalBaconUI.init(container, renderer, scene, camera);
        DigitalBaconUI.InputHandler.enableXRControllerManagement(userRig);
    }
    
    update(frame)   {
        DigitalBaconUI.update(frame);
    }

    show() {
        this.isShown = true;
        this.body.position.set(0, 1.7, -1);
        this.body.scale.set(0.5, 0.5, 0.5);
        this.userRig.add(this.body);
    }
    hide() {
        this.isShown = false;
        this.userRig.remove(this.body);
    }
    toggle() {
        if(this.isShown) this.hide(); else this.show();
    }

    constructor(scene, userRig, settings, starfield, sim, telescope) {

        this.isShown = false;
        this.scene = scene;
        this.userRig = userRig;
        this.glass = false;

        const body = new DigitalBaconUI.Body({
            borderRadius: 0.05,
            borderWidth: 0.001,
            glassmorphism: this.glass,
            justifyContent: 'spaceBetween',
            width: 1.5,
          });
          const row1 = new DigitalBaconUI.Span({
            borderTopLeftRadius: 0.05,
            borderTopRightRadius: 0.05,
            height: 1/4,
            width: '100%',
            justifyContent: 'center',
          });
          body.add(row1);

          const row2 = new DigitalBaconUI.Span({
            height: 1/2,
            width: '90%',
            glassmorphism: this.glass,
            justifyContent: 'center',
            backgroundVisible: true,
            materialColor: '#aaaaaa',
          });
          body.add(row2);

          const row3 = new DigitalBaconUI.Div({
            borderBottomLeftRadius: 0.05,
            borderBottomRightRadius: 0.05,
            justifyContent: 'center',
            height: 1/4,
            width: '100%',
          });
          body.add(row3);

          const text1 = new DigitalBaconUI.Text('Input Buttons and Range', {
            fontSize: 0.1,
            color: '#ffffff',
          });
          row1.add(text1);

          const section1 = new DigitalBaconUI.Div({
            alignItems: 'start',
            padding: 0.05,
            height: '100%',
            width: '50%',
          });
          row2.add(section1);

          const section2 = new DigitalBaconUI.Div({
            padding: 0.05,
            height: '100%',
            width: '50%',
          });
          row2.add(section2);

          const labelStyle = new DigitalBaconUI.Style({
            color: '#ffffff',
            fontSize: 0.07,
            marginLeft: 0.02,
          });
          
          function createElement(parent, element, label, value, onChangeCallback) {
            const span = new DigitalBaconUI.Span();
            const labelText = new DigitalBaconUI.Text(label, labelStyle);
            span.add(element);
            span.add(labelText);
            element.onChange = (value) => onChangeCallback(value);
            parent.add(span);
            return span;
          }

          createElement(section1, 
              new DigitalBaconUI.Toggle(), 
              'Gravity', settings.gravity, 
              (value) => {settings.gravity = value;}
          );
          createElement(section1, 
              new DigitalBaconUI.Checkbox(), 
              'Stars', settings.showStars, 
              (value) => {
                settings.showStars = value; 
                starfield.enableCatalogs('star',value);
              }
          );
          createElement(section1, 
              new DigitalBaconUI.Checkbox(), 
              'Galaxies', settings.showGalaxies, 
              (value) => {
                settings.showGalaxies = value; 
                starfield.enableCatalogs('galaxy',value);
              }
          );

          createElement(section1, 
              new DigitalBaconUI.Checkbox(), 
              'Nebulae', settings.showNebulae, 
              (value) => {
                settings.showNebulae = value; 
                starfield.enableCatalogs('nebula',value);
              }
          );
          createElement(section1, 
              new DigitalBaconUI.Checkbox(), 
              'Clusters', settings.showClusters,
              (value) => {
                settings.showClusters = value;
                starfield.enableCatalogs('cluster',value);
              }
          );
          createElement(section1, 
              new DigitalBaconUI.Checkbox(), 
              'Images', settings.showImages,
              (value) => {
                settings.showImages = value;
                starfield.enableCatalogs('image',value);
              }
          );
          createElement(section1, 
              new DigitalBaconUI.Checkbox(), 
              'Ground', settings.showGround,
              (value) => {
                settings.showGround = value;
                sim.ground.visible = value;
              }
          );


/*          const toggle2 = new DigitalBaconUI.Toggle({ borderRadius: 0.04 });
          const toggle2Span = new DigitalBaconUI.Span();
          const toggle2Label = new DigitalBaconUI.Text('Toggle', labelStyle);

          const checkbox1 = new DigitalBaconUI.Checkbox();
          const checkbox1Span = new DigitalBaconUI.Span();
          const checkbox1Label = new DigitalBaconUI.Text('Checkbox', labelStyle);
          const checkbox2 = new DigitalBaconUI.Checkbox({ borderRadius: 0.04 });
          const checkbox2Span = new DigitalBaconUI.Span();
          const checkbox2Label = new DigitalBaconUI.Text('Checkbox', labelStyle);
          const radio1 = new DigitalBaconUI.Radio('radioName');
          const radio1Span = new DigitalBaconUI.Span();
          const radio1Label = new DigitalBaconUI.Text('Radio', labelStyle);
          const radio2 = new DigitalBaconUI.Radio('radioName');
          const radio2Span = new DigitalBaconUI.Span();
          const radio2Label = new DigitalBaconUI.Text('Radio', labelStyle);
          const radio3 = new DigitalBaconUI.Radio('radioName');
          const radio3Span = new DigitalBaconUI.Span();
          const radio3Label = new DigitalBaconUI.Text('Radio', labelStyle);
          section1.add(toggleGSpan);
          section1.add(toggle2Span);
          section1.add(checkbox1Span);
          section1.add(checkbox2Span);
          section2.add(radio1Span);
          section2.add(radio2Span);
          section2.add(radio3Span);
          toggle2Span.add(toggle2);
          toggle2Span.add(toggle2Label);
          checkbox1Span.add(checkbox1);
          checkbox1Span.add(checkbox1Label);
          checkbox2Span.add(checkbox2);
          checkbox2Span.add(checkbox2Label);
          radio1Span.add(radio1);
          radio1Span.add(radio1Label);
          radio2Span.add(radio2);
          radio2Span.add(radio2Label);
          radio3Span.add(radio3);
          radio3Span.add(radio3Label);
          */
          
          const range = new DigitalBaconUI.Range({ width: 1 });
          const rangeLabel = new DigitalBaconUI.Text('Range', {
            color: '#ffffff',
            fontSize: 0.07,
          });
          row3.add(rangeLabel);
          row3.add(range);
    
          range.onChange = (value) => {
            row2.material.color.setHSL(0, 0, 1 - value);
          };
          range.value = 0.5;
     
          row2.material.color.setHSL(0, 0, 0.5);

          this.body = body;
    }
}    